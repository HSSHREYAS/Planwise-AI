"""
PlanWise AI - Planning Agent

Core agent implementing the Python state machine.

State machine:
    RECEIVED → UNDERSTANDING → DECOMPOSING → EXECUTING →
    PLANNING → VALIDATING → VERIFYING → COMPLETED

Branches:
    MISSING_INFORMATION → WAITING_FOR_USER
    CONSTRAINT_VIOLATION → REPLANNING → VALIDATING
    ERROR → CONTROLLED_RECOVERY

The LLM (a hosted, free-tier API) handles language: understanding the
request, composing the plan and wording the answer. Everything that must
be exact - locations, dates, budgets, grounding - is done in Python.
"""

import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app import money
from app.agent import prompts
from app.config import MAX_REPLAN_ATTEMPTS, MAX_TRIP_DAYS
from app.geo import geocoder
from app.geo.geocoder import Place
from app.llm.client import LLMClient, get_llm_client
from app.models.schemas import (
    AgentResponse,
    AgentStatus,
    ConstraintResult,
    IntentResult,
    Plan,
    PlanActivity,
    PlanDay,
    PlanState,
    PlanTimeSlot,
    ResponseStatus,
    Task,
    TaskStatus,
    normalize_iso_date,
)
from app.state.manager import StateManager
from app.tools import common as tool_common
from app.tools.registry import execute_tool
from app.validation.constraints import check_impossible_constraints, validate_plan
from app.validation.verifier import verify_plan

logger = logging.getLogger(__name__)

SEARCH_INTENTS = ("hotel_search", "restaurant_search", "attraction_search", "transport_search")
SCHEDULE_INTENTS = ("study_planning", "schedule_generation")
PLANNING_INTENTS = ("trip_planning",) + SCHEDULE_INTENTS
KNOWN_INTENTS = SEARCH_INTENTS + PLANNING_INTENTS + ("replanning", "general_query")

SLOT_ORDER = ("morning", "afternoon", "evening")
DEFAULT_SLOT_TIMES = {"morning": "09:30", "afternoon": "13:30", "evening": "18:30"}

# Phrases that mean "where I am" rather than naming a place
_NEAR_ME = re.compile(
    r"\b(near\s*me|nearby|near\s*by|around\s+me|around\s+here|close\s+to\s+me|"
    r"my\s+(current\s+)?location|where\s+i\s+am|near\s+here)\b",
    re.IGNORECASE,
)
_VERBS_NOT_PLACES = {
    "stay", "eat", "visit", "see", "go", "explore", "relax", "shop", "dine", "sleep",
    "travel", "plan", "book", "find", "show", "try", "spend", "hang", "chill", "party",
}
_NOT_A_PLACE = {
    "me", "here", "nearby", "near me", "my location", "current location",
    "my current location", "the area", "town", "the city", "the centre", "the center",
    "today", "tomorrow", "tonight", "day", "days", "budget", "morning", "evening",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}
_FRUGAL_NOTICE = (
    "Running on the free keyless AI endpoint (about one AI reply every 45 seconds). "
    "Add a free GROQ_API_KEY or GEMINI_API_KEY to .env for instant, full AI answers."
)


class PlanningAgent:
    """
    Core planning agent with explicit state machine transitions.

    understand → resolve context → check missing → decompose →
    execute tools → generate plan → validate → verify → respond
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or get_llm_client()
        self.state_manager = StateManager()

    # ════════════════════════════════════════════════════════════
    # Main entry point
    # ════════════════════════════════════════════════════════════

    def handle_message(
        self,
        message: str,
        state: PlanState,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """
        Process a user message through the full state machine.

        Args:
            message: The user's natural language message
            state: Session state (mutated in place)
            context: Optional UI context - location/lat/lon picked in the
                search bar (or the user's current location) and travel dates
        """
        logger.info(f"Processing message: '{message[:100]}'")
        context = context or {}

        state = self.state_manager.add_message(state, "user", message)
        state = self.state_manager.set_goal(state, message)
        intent: Optional[IntentResult] = None

        try:
            # ─── UNDERSTANDING ───────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.UNDERSTANDING)
            intent = self._understand(message, state)

            previous_intent = state.intent
            previous_place = dict(state.place) if state.place else None
            previous_travelers = state.travelers
            had_plan = state.current_plan is not None

            is_modification = bool(intent.is_modification and had_plan)
            if intent.intent == "replanning":
                is_modification = had_plan
                if not had_plan:
                    intent.intent = "trip_planning"

            if intent.intent in SEARCH_INTENTS:
                is_modification = False   # looking something up never edits the plan

            state = self.state_manager.update_from_intent(state, intent)
            self._resolve_travelers(state, intent, context)

            # "we are 4 people now" on an existing trip plan = change that plan
            if (
                had_plan
                and state.travelers != previous_travelers
                and previous_intent == "trip_planning"
                and not intent.location
                and intent.intent in ("general_query", "trip_planning", "replanning")
            ):
                is_modification = True
            if is_modification and previous_intent in PLANNING_INTENTS:
                # A change request keeps the kind of plan being worked on
                state.intent = previous_intent

            # ─── RESOLVE LOCATION / DATES / CURRENCY ─────────────
            location_problem = self._resolve_location(state, intent, context, message)
            self._resolve_dates(state, intent, context)
            self._resolve_currency(state, intent, message)

            if location_problem and (state.intent != "general_query" or is_modification):
                return self._respond(
                    state, ResponseStatus.CLARIFICATION_REQUIRED, location_problem, intent=intent
                )

            # ─── GENERAL CONVERSATION ────────────────────────────
            if state.intent == "general_query" and not is_modification:
                return self._handle_general(message, state, intent)

            # ─── MODIFY EXISTING PLAN ────────────────────────────
            if is_modification:
                location_changed = (state.place or None) != previous_place and state.place is not None
                return self._handle_replanning(state, intent, location_changed)

            # ─── CHECK MISSING INFO ──────────────────────────────
            missing = self._check_missing_info(state)
            if missing:
                state = self.state_manager.set_status(state, AgentStatus.WAITING_FOR_USER)
                return self._respond(
                    state,
                    ResponseStatus.CLARIFICATION_REQUIRED,
                    prompts.clarification_text(missing),
                    intent=intent,
                )

            impossible_warnings = check_impossible_constraints(state)

            # ─── DECOMPOSING ─────────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.DECOMPOSING)
            tasks = self._decompose(state)
            state = self.state_manager.set_subtasks(state, tasks)

            # ─── EXECUTING (TOOL CALLS) ──────────────────────────
            if tasks:
                state = self.state_manager.set_status(state, AgentStatus.EXECUTING)
                state.tool_results = []
                state.chosen_options = {}
                state = self._execute_tools(tasks, state)

            # ─── DIRECT SEARCH RESULTS PATH ──────────────────────
            if self._is_single_domain_search(state):
                return self._handle_search_results(state, intent, impossible_warnings)

            # ─── PLANNING → VALIDATING → VERIFYING ───────────────
            return self._plan_and_respond(state, intent, impossible_warnings)

        except Exception as e:
            logger.error(f"Unexpected agent error: {e}", exc_info=True)
            state = self.state_manager.set_status(state, AgentStatus.ERROR)
            return self._respond(
                state,
                ResponseStatus.ERROR,
                "Something went wrong while processing your request. "
                "Please try again or rephrase your request.",
                intent=intent,
            )

    # ════════════════════════════════════════════════════════════
    # Understanding
    # ════════════════════════════════════════════════════════════

    def _understand(self, message: str, state: PlanState) -> IntentResult:
        """UNDERSTANDING state: extract intent and parameters."""
        if self.llm.frugal:
            # One AI reply per ~45s on the keyless endpoint: keep it for the answer
            return self._fallback_intent(message, state)

        conversation_summary = self.state_manager.get_conversation_summary(state)
        prompt = prompts.intent_prompt(message, conversation_summary)

        try:
            result = self.llm.generate_structured(
                prompt=prompt,
                schema=IntentResult,
                system="You are a planning intent extraction system. Respond with JSON only.",
            )
        except Exception as e:  # LLM down, rate limited or returned junk
            logger.warning(f"LLM intent extraction failed, using rules: {str(e)[:120]}")
            return self._fallback_intent(message, state)

        # Cross-check the model with the rule-based reading of the same message
        rule = self._fallback_intent(message, state)
        if result.intent not in KNOWN_INTENTS:
            result.intent = rule.intent
        # "show me places to stay / eat ..." is a search even when a plan already
        # exists - never turn it into a rewrite of that plan
        names_a_plan = re.search(r"\b(plan|itinerary|trip|schedule|tour)\b", message.lower())
        if rule.intent in SEARCH_INTENTS and result.intent not in SEARCH_INTENTS and not names_a_plan:
            result.intent = rule.intent
            result.is_modification = False
        # Numbers the model skipped are taken from the rules (never overwritten)
        if result.travelers is None:
            result.travelers = rule.travelers
        if result.budget is None and rule.budget is not None:
            result.budget = rule.budget
            result.budget_per_person = rule.budget_per_person
        if result.duration_days is None:
            result.duration_days = rule.duration_days
        for pref in rule.preferences:
            if pref not in result.preferences:
                result.preferences.append(pref)

        if result.location and not self._looks_like_place(result.location):
            result.location = None
        logger.info(f"Intent extracted: {result.intent} (location={result.location})")
        return result

    @staticmethod
    def _looks_like_place(text: str) -> bool:
        cleaned = text.strip().lower().strip(".,!?")
        # "places to stay", "where to eat" ... the word after "to" is a verb, not a city
        first_word = cleaned.split()[0] if cleaned else ""
        if first_word in _VERBS_NOT_PLACES:
            return False
        if not cleaned or cleaned in _NOT_A_PLACE or _NEAR_ME.search(cleaned):
            return False
        if tool_common.strip_area_words(cleaned).lower() in tool_common.LOCAL_AREAS:
            return False
        return len(cleaned) >= 2 and not cleaned.isdigit()

    def _fallback_intent(self, message: str, state: PlanState) -> IntentResult:
        """Rule-based intent detection (used when the LLM is unavailable)."""
        msg_lower = message.lower()

        def has(*words: str) -> bool:
            return any(re.search(rf"\b{re.escape(w)}", msg_lower) for w in words)

        intent = "general_query"
        asks_advice = bool(re.search(
            r"\b(best time|when (should|to|is)|what time of year|weather|climate|how (do|to|much|many|long|far|safe)|"
            r"is it (safe|worth|expensive)|what (should i|to) (pack|wear|carry)|tips|advice|visa|"
            r"tell me about|what is|who is|why)\b", msg_lower,
        )) and not has("find", "show", "list", "search", "recommend", "suggest", "plan", "itinerary")
        if asks_advice:
            pass
        elif has("study", "exam", "revision", "revise", "syllabus", "homework") or (
            has("schedule", "timetable", "routine") and not has("trip", "travel", "itinerary")
        ):
            intent = "study_planning"
        elif (
            has("itinerary", "trip", "tour", "getaway", "vacation", "holiday")
            or (has("plan") and has("day", "weekend", "visit", "travel"))
        ):
            intent = "trip_planning"
        elif has("hotel", "stay", "accommodation", "guesthouse", "guest house", "hostel", "b&b", "lodge", "resort"):
            intent = "hotel_search"
        elif has("restaurant", "food", "eat", "dining", "dine", "lunch", "dinner", "breakfast", "cafe", "pub", "cuisine"):
            intent = "restaurant_search"
        elif has("train", "taxi", "transport", "bus", "airport", "flight", "railway", "metro", "station"):
            intent = "transport_search"
        elif has("attraction", "visit", "see", "sight", "museum", "park", "temple", "things to do",
                 "places", "landmark", "monument", "palace", "fort", "beach", "explore"):
            intent = "attraction_search"
        elif re.search(r"\b\d+\s*[- ]?\s*days?\b", msg_lower):
            intent = "trip_planning"  # "3 days in Goa"

        # Modification of an existing plan
        is_mod = False
        if has("change", "reduce", "increase", "modify", "update", "instead", "actually",
               "make it", "add ", "remove", "replace", "swap", "cheaper", "extend", "shorten"):
            is_mod = state.current_plan is not None

        location = self._extract_location(message)

        # Budget: needs a budget keyword or an explicit currency marker, so
        # "2 day" or "Day 1" is never captured as a budget
        budget = None
        budget_match = re.search(
            r"(?:[₹$£€]\s*|(?:budget|cost|spend|price|under|max|within|below)\s*"
            r"(?:of|is|to|around|about)?\s*(?:rs\.?|inr|usd|gbp|eur)?\s*[₹$£€]?\s*)(\d[\d,]*(?:\.\d+)?)(?![\d,.:])"
            r"\s*(k\b)?(?!\s*[- ]?(?:days?|nights?|hours?|hrs?|km|stars?|people|persons?|travell?ers?|adults|pax|guests|friends|members|pm|am)\b)",
            message,
            re.IGNORECASE,
        )
        if not budget_match:
            budget_match = re.search(
                r"(\d[\d,]*(?:\.\d+)?)\s*(k\b)?\s*(?:rupees|inr|rs\b|dollars|usd|pounds|gbp|euros?|eur|bucks)",
                message,
                re.IGNORECASE,
            )
        if budget_match:
            try:
                budget = float(budget_match.group(1).replace(",", ""))
                if budget_match.group(2):
                    budget *= 1000
            except ValueError:
                budget = None

        # Duration ("3 days", "3-day", "weekend", "a week" ...)
        duration = None
        duration_match = re.search(r"(\d+)\s*[-_ ]?\s*days?\b", msg_lower)
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
        word_match = re.search(r"\b(one|two|three|four|five|six|seven)[\s-]days?\b", msg_lower)
        if duration_match:
            duration = int(duration_match.group(1))
        elif word_match:
            duration = words[word_match.group(1)]
        elif "weekend" in msg_lower:
            duration = 2
        elif re.search(r"\b(a|one|1)\s+week\b", msg_lower):
            duration = 7
        elif re.search(r"\b(day\s*trip|today|tomorrow)\b", msg_lower) and intent == "trip_planning":
            duration = 1

        # Dates written as YYYY-MM-DD
        iso_dates = [normalize_iso_date(d) for d in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message)]
        iso_dates = [d for d in iso_dates if d]
        start_date = iso_dates[0] if iso_dates else None
        end_date = iso_dates[1] if len(iso_dates) > 1 else None
        if not start_date:
            if re.search(r"\btomorrow\b", msg_lower):
                start_date = (date.today() + timedelta(days=1)).isoformat()
            elif re.search(r"\b(today|tonight)\b", msg_lower):
                start_date = date.today().isoformat()

        preferences = []
        pref_words = [
            "vegetarian", "vegan", "cheap", "budget-friendly", "luxury", "wifi", "parking",
            "family", "romantic", "halal", "gluten-free", "hostel", "resort", "cafe", "pub",
        ] + [
            "indian", "chinese", "italian", "thai", "japanese", "mexican", "french",
            "korean", "mediterranean", "seafood", "pizza", "sushi", "biryani",
        ]
        for word in pref_words:
            if re.search(rf"\b{re.escape(word)}\b", msg_lower):
                preferences.append(word)
        if re.search(r"\bveg\b", msg_lower) and "vegetarian" not in preferences:
            preferences.append("vegetarian")
        # "budget hotels", "budget-friendly", "on a budget" = cheap;
        # "with proper budget" / "budget breakdown" are not a price preference
        if re.search(
            r"\b(budget[- ](?:friendly|hotels?|stays?|trip|options?|places?|restaurants?|food|travel)"
            r"|on\s+a\s+(?:tight\s+)?budget|affordable|inexpensive|low[- ]cost)\b",
            msg_lower,
        ) and budget is None \
                and "cheap" not in preferences:
            preferences.append("cheap")
        star_match = re.search(r"\b([3-5])[- ]?star", msg_lower)
        if star_match:
            preferences.append(f"{star_match.group(1)}-star")

        interests = []
        for word in ["museum", "history", "historic", "nature", "park", "temple", "art", "culture",
                     "shopping", "architecture", "beach", "nightlife", "religious", "family", "free",
                     "college", "church", "palace", "fort", "wildlife", "adventure"]:
            if re.search(rf"\b{word}s?\b", msg_lower):
                interests.append(word)

        travelers = self._extract_travelers(msg_lower)
        budget_per_person = budget is not None and bool(re.search(
            r"\b(per\s+person|per\s+head|a\s+head|each|apiece|per\s+traveller|per\s+traveler|pp)\b"
            r"|/\s*(person|head)", msg_lower,
        ))

        raw_changes: Dict[str, Any] = {}
        if is_mod:
            if budget is not None:
                raw_changes["budget"] = budget
            if duration is not None:
                raw_changes["duration_days"] = duration

        return IntentResult(
            travelers=travelers,
            budget_per_person=budget_per_person,
            intent=intent,
            location=location,
            budget=budget,
            duration_days=duration,
            start_date=start_date,
            end_date=end_date,
            currency=money.detect_currency(message),
            preferences=preferences,
            interests=interests,
            is_modification=is_mod,
            raw_changes=raw_changes or None,
        )

    @staticmethod
    def _extract_travelers(msg_lower: str) -> Optional[int]:
        """Group size mentioned in a message ("for 4 people", "family of 5", "solo")."""
        number_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        }
        num = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        people = r"(?:people|persons?|travell?ers?|adults|pax|guests|members|friends|of\s+us|folks|heads)"
        patterns = [
            rf"\b{num}\s+{people}\b",
            rf"\b(?:group|family|party|team|gang)\s+of\s+{num}\b",
            rf"\bwe\s+are\s+(?:a\s+group\s+of\s+)?{num}\b(?!\s*(?:days?|nights?))",
            rf"\b(?:for|with)\s+{num}\s+(?:of\s+us|in\s+total|altogether)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, msg_lower)
            if match:
                raw = match.group(1)
                value = number_words.get(raw) or (int(raw) if raw.isdigit() else None)
                if value:
                    return money.clamp_travelers(value)

        if re.search(r"\b(solo|alone|by myself|just me|on my own)\b", msg_lower):
            return 1
        if re.search(r"\b(couple|honeymoon|with my (wife|husband|partner|girlfriend|boyfriend|spouse))\b",
                     msg_lower):
            return 2
        return None

    def _extract_location(self, message: str) -> Optional[str]:
        """Find a place name in free text without an LLM."""
        if "cambridge" in message.lower():
            return "cambridge"

        stop = r"(?=\s+(?:for|with|under|on|from|next|this|during|and|in\s+\d|within|that|which|having|" \
               r"before|after|arriving|leaving|at\s+\d|between|by|budget|to\s+\w+\s+for)\b|[,.!?;:]|$)"

        # "... in Paris", "trip to New Delhi", "near Mysuru Palace" (capitalised names)
        match = re.search(
            r"\b(?:in|to|at|near|around|of|visit|visiting|explore|exploring)\s+"
            r"((?:[A-Z][\w'’.-]*)(?:\s+(?:[A-Z][\w'’.-]*|de|del|la|el|of|the|di|da)){0,4})",
            message,
        )
        candidate = match.group(1).strip() if match else None

        # lower-case typing: "trip to goa for 3 days"
        if not candidate:
            match = re.search(
                r"\b(?:trip|travel|go|going|visit|itinerary|tour|hotels?|stays?|restaurants?|food|eat|"
                r"attractions?|places|sights?|things to do|museums?|parks?|trains?|transport|plan)\s+"
                r"(?:to|in|at|near|around|for)\s+(?:the\s+city\s+of\s+)?([a-z][a-z .'’-]{1,40}?)" + stop,
                message.lower(),
            )
            candidate = match.group(1).strip() if match else None

        if not candidate:
            return None
        candidate = re.sub(r"\s+", " ", candidate).strip(" .,'")
        candidate = re.sub(r"^(the|a|an)\s+", "", candidate, flags=re.IGNORECASE)
        if not self._looks_like_place(candidate):
            return None
        return candidate.lower()

    # ════════════════════════════════════════════════════════════
    # Context resolution (location, dates, currency)
    # ════════════════════════════════════════════════════════════

    def _resolve_location(
        self,
        state: PlanState,
        intent: IntentResult,
        context: Dict[str, Any],
        message: str,
    ) -> Optional[str]:
        """
        Decide which place this request is about and geocode it.

        Priority:
          1. a place named in the message
          2. the place picked in the UI (search bar / location chip / GPS)
          3. the place already established in this session

        Returns a clarification message if a named place cannot be located.
        """
        ctx_location = (context.get("location") or "").strip() or None
        ctx_lat, ctx_lon = context.get("lat"), context.get("lon")
        ctx_has_coords = ctx_lat is not None and ctx_lon is not None

        named = intent.location if intent.location and self._looks_like_place(intent.location) else None
        wants_here = bool(_NEAR_ME.search(message))

        # 1. Place named in the message (unless it is the place we already have)
        if named and not (wants_here and ctx_has_coords):
            if state.place and self._same_place_name(named, state.place):
                state.location = state.place.get("label") or state.place.get("name")
                return None
            if ctx_has_coords and ctx_location and self._same_place_name(named, {"name": ctx_location}):
                self._set_place(state, self._place_from_context(ctx_location, ctx_lat, ctx_lon))
                return None

            query = tool_common.strip_area_words(named)
            place = geocoder.geocode(query)
            if place is not None:
                self._set_place(state, place)
                if tool_common.local_area(named) and geocoder.is_cambridge_uk(place):
                    state.location = named  # keep "centre of cambridge" for area filtering
                return None
            if geocoder.service_ok():
                state.location = state.place.get("label") if state.place else None
                return (
                    f"I couldn't find **{named.title()}** on the map. Could you check the spelling, "
                    f"or add the region or country (for example \"Springfield, Illinois\")?"
                )
            # Map service is down: keep the name, answers fall back to AI knowledge
            state.location = named.title()
            state.place = None
            return None

        # 2. Place supplied by the UI
        if ctx_has_coords or ctx_location:
            if ctx_has_coords:
                place = self._place_from_context(ctx_location, ctx_lat, ctx_lon)
            else:
                place = geocoder.geocode(ctx_location)
            if place is not None:
                explicit = bool(context.get("explicit")) or wants_here
                if explicit or not state.place:
                    self._set_place(state, place)
                return None

        # 3. Keep whatever the session already has
        if state.place:
            state.location = state.place.get("label") or state.place.get("name")
        return None

    @staticmethod
    def _same_place_name(name: str, place: Dict[str, Any]) -> bool:
        wanted = tool_common.strip_area_words(name).strip().lower()
        known = str(place.get("name") or "").strip().lower()
        label = str(place.get("label") or "").strip().lower()
        if not wanted or not known:
            return False
        return wanted == known or wanted == label or wanted == known.split(",")[0].strip()

    @staticmethod
    def _place_from_context(location: Optional[str], lat: float, lon: float) -> Place:
        place = geocoder.lookup(lat, lon) or geocoder.reverse(lat, lon)
        if place is None:  # map service unreachable: trust the coordinates
            return Place(name=location or "Selected location", lat=float(lat), lon=float(lon))
        if location:
            short = location.split(",")[0].strip()
            if short and short.lower() != place.name.lower() and place.kind != "current_location":
                place = place.model_copy(update={"name": short})
        return place

    @staticmethod
    def _set_place(state: PlanState, place: Place) -> None:
        data = place.model_dump()
        data["label"] = place.label
        if state.place and (
            round(state.place.get("lat", 0), 3) != round(place.lat, 3)
            or round(state.place.get("lon", 0), 3) != round(place.lon, 3)
        ):
            logger.info(f"Location changed: {state.place.get('label')} → {place.label}")
            state.tool_results = []
            state.chosen_options = {}
        state.place = data
        state.location = place.label

    def _resolve_dates(self, state: PlanState, intent: IntentResult, context: Dict[str, Any]) -> None:
        """Merge dates from the message and the UI; keep duration consistent."""
        ctx_start = normalize_iso_date(context.get("start_date"))
        ctx_end = normalize_iso_date(context.get("end_date"))

        start = intent.start_date or ctx_start
        end = intent.end_date or ctx_end
        message_duration = intent.duration_days

        if start:
            state.start_date = start
        if end:
            state.end_date = end

        if state.start_date and state.end_date:
            first, last = date.fromisoformat(state.start_date), date.fromisoformat(state.end_date)
            if last < first:
                first, last = last, first
            if message_duration and not intent.end_date:
                # "3 days starting 12 Dec" - the stated length wins over the UI range
                last = first + timedelta(days=message_duration - 1)
            span = (last - first).days + 1
            if span > MAX_TRIP_DAYS:
                span = MAX_TRIP_DAYS
                last = first + timedelta(days=span - 1)
            state.start_date, state.end_date = first.isoformat(), last.isoformat()
            if start or end or message_duration:
                state.duration_days = span
        elif state.start_date and state.duration_days:
            first = date.fromisoformat(state.start_date)
            state.end_date = (first + timedelta(days=state.duration_days - 1)).isoformat()

        if state.duration_days is not None:
            state.duration_days = max(1, min(int(state.duration_days), MAX_TRIP_DAYS))
            if state.start_date:
                first = date.fromisoformat(state.start_date)
                state.end_date = (first + timedelta(days=state.duration_days - 1)).isoformat()

        if state.start_date and state.end_date:
            state.dates = f"{state.start_date} to {state.end_date}"

    def _resolve_travelers(self, state: PlanState, intent: IntentResult, context: Dict[str, Any]) -> None:
        """
        Group size: a number in the message wins, then the UI selector, then
        the session's earlier value. Budgets are kept as the group total, so a
        per-person budget ("5000 each") is multiplied out here.
        """
        if intent.travelers:
            state.travelers = money.clamp_travelers(intent.travelers)
        elif context.get("travelers"):
            state.travelers = money.clamp_travelers(context["travelers"])
        else:
            state.travelers = money.clamp_travelers(state.travelers or 1)

        if intent.budget is not None and intent.budget_per_person:
            state.budget = float(intent.budget) * state.travelers

    def _resolve_currency(self, state: PlanState, intent: IntentResult, message: str) -> None:
        explicit = intent.currency or money.detect_currency(message)
        if explicit:
            state.currency = explicit
            return
        if state.budget is not None and state.currency:
            return  # keep the currency the budget was stated in
        if state.place and state.place.get("country_code"):
            state.currency = money.currency_for_country(state.place["country_code"])
        elif not state.currency and state.location and "cambridge" in state.location.lower():
            state.currency = "GBP"

    # ════════════════════════════════════════════════════════════
    # General conversation
    # ════════════════════════════════════════════════════════════

    def _handle_general(self, message: str, state: PlanState, intent: IntentResult) -> AgentResponse:
        state = self.state_manager.set_status(state, AgentStatus.COMPLETED)
        history = [
            {"role": m.role if m.role in ("user", "assistant") else "user", "content": m.content[:600]}
            for m in state.conversation_history[-7:-1]
        ]
        try:
            text = self.llm.generate(
                prompt=prompts.general_prompt(message, self.state_manager.get_state_summary(state)),
                system=prompts.SYSTEM_ASSISTANT,
                temperature=0.5,
                max_tokens=700,
                history=history,
            )
            return self._respond(state, ResponseStatus.COMPLETED, text, intent=intent)
        except Exception as e:
            logger.warning(f"General answer failed: {str(e)[:120]}")
            where = f" in **{state.location}**" if state.location else ""
            text = (
                "The AI model is busy right now, so I can't write a full answer to that - "
                "but live search and planning still work. Try one of these:\n\n"
                f"- \"Find vegetarian restaurants{where}\"\n"
                f"- \"Top attractions{where}\"\n"
                f"- \"Plan a 2-day trip{where or ' to Jaipur'}\"\n"
                "- \"Create a 3-day study schedule for maths and physics\""
            )
            return self._respond(
                state, ResponseStatus.COMPLETED, text, intent=intent,
                notice=_FRUGAL_NOTICE if self.llm.frugal else None,
            )

    # ════════════════════════════════════════════════════════════
    # Missing info, decomposition, tool execution
    # ════════════════════════════════════════════════════════════

    def _check_missing_info(self, state: PlanState) -> Optional[List[str]]:
        """Essential information that must be known before planning/searching."""
        missing = []
        if state.intent == "trip_planning":
            if not state.location:
                missing.append("location")
            if not state.duration_days:
                missing.append("duration")
        elif state.intent in SEARCH_INTENTS:
            if not state.location:
                missing.append("location")
        return missing or None

    def _decompose(self, state: PlanState) -> List[Task]:
        """DECOMPOSING state: deterministic mapping from intent to tool calls."""
        location = state.location
        place = state.place
        level = tool_common.price_level(None, state.preferences)

        # The bundled Cambridge dataset is organised by area (centre, north ...)
        if place and geocoder.is_cambridge_uk(Place.model_validate(place)):
            area = tool_common.local_area(state.goal or "")
            if area:
                location = f"{area} of Cambridge"

        def task(tool: str, **params: Any) -> Task:
            return Task(task_type=tool, parameters={"location": location, "place": place, **params})

        if state.intent == "hotel_search":
            return [task("hotel_search", budget=level, preferences=state.preferences)]
        if state.intent == "restaurant_search":
            return [task("restaurant_search", budget=level, preferences=state.preferences)]
        if state.intent == "attraction_search":
            return [task("attraction_search", interests=state.interests)]
        if state.intent == "transport_search":
            route = re.search(
                r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:arriving|leaving|departing|on|at|before|after|by|for)\b|[,.?!]|$)",
                state.goal or "", re.IGNORECASE,
            )
            source = route.group(1).strip().lower() if route else None
            destination = route.group(2).strip().lower() if route else None
            if "cambridge" in f"{source} {destination}" or "cambridge" in (state.goal or "").lower():
                # Train timetables exist only in the bundled Cambridge dataset
                return [Task(task_type="transport_search", parameters={
                    "location": "cambridge", "source": source, "destination": destination,
                })]
            return [task("transport_search")]
        if state.intent == "trip_planning":
            tasks = [
                task("attraction_search", interests=state.interests),
                task("restaurant_search", budget=level, preferences=state.preferences),
            ]
            if (state.duration_days or 1) > 1:
                tasks.append(task("hotel_search", budget=level, preferences=state.preferences))
            return tasks
        return []  # study / schedule plans need no tools

    def _execute_tools(self, tasks: List[Task], state: PlanState) -> PlanState:
        """EXECUTING state: run tools for each task."""
        import app.tools  # noqa: F401  (registers all tools)

        for task in tasks:
            logger.info(f"Executing tool: {task.task_type}")
            result = execute_tool(task.task_type, task.parameters)
            task.result = None  # results live in state.tool_results
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            state = self.state_manager.update_from_tool_result(state, result)
        return state

    def _data_source(self, state: PlanState) -> str:
        sources = {
            r.get("source") for records in state.chosen_options.values() for r in records
        }
        if "openstreetmap" in sources:
            return "openstreetmap"
        if "multiwoz" in sources:
            return "multiwoz"
        return "ai_knowledge"

    def _data_source_label(self, state: PlanState) -> str:
        return {
            "openstreetmap": "live OpenStreetMap data",
            "multiwoz": "MultiWOZ 2.2 Cambridge dataset",
            "ai_knowledge": "no verified data available",
        }[self._data_source(state)]

    # ════════════════════════════════════════════════════════════
    # Single-domain search
    # ════════════════════════════════════════════════════════════

    def _is_single_domain_search(self, state: PlanState) -> bool:
        return state.intent in SEARCH_INTENTS

    def _handle_search_results(
        self, state: PlanState, intent: IntentResult, warnings: List[str]
    ) -> AgentResponse:
        """Answer a single-domain search from live data, worded by the LLM."""
        state = self.state_manager.set_status(state, AgentStatus.COMPLETED)
        domain = state.intent.replace("_search", "")
        location = state.location or "the selected area"
        constraints = self._build_constraints_summary(state)
        warnings = list(warnings)

        results: List[Dict[str, Any]] = []
        lookup_failed = False
        for tr in state.tool_results:
            if tr.success:
                results.extend(tr.results)
            else:
                lookup_failed = True

        notice = None
        results = self._annotate_group_costs(domain, results, state)

        # No verified results → honest AI-knowledge suggestions
        if not results:
            try:
                text = self.llm.generate(
                    prompt=prompts.knowledge_search_prompt(domain, state.goal or "", location, constraints),
                    system=prompts.SYSTEM_ASSISTANT,
                    temperature=0.4,
                    max_tokens=600,
                )
                reason = (
                    "Live map data is temporarily unavailable"
                    if lookup_failed else f"No mapped {domain} results were found for {location}"
                )
                warnings.append(f"{reason} - these are AI suggestions, not verified listings.")
            except Exception:
                text = (
                    f"I couldn't find any {domain} options for **{location}** right now"
                    + (" because the live map service is not responding" if lookup_failed else "")
                    + ". Try a nearby larger town, a different category, or ask again in a moment."
                )
            return self._respond(
                state, ResponseStatus.COMPLETED, text, intent=intent,
                validation=ConstraintResult(valid=True, violations=[], warnings=warnings),
            )

        options_summary = self.state_manager.get_retrieved_options_summary(state)
        try:
            text = self.llm.generate(
                prompt=prompts.search_results_prompt(
                    domain, options_summary, state.goal or "", location, constraints
                ),
                system=prompts.SYSTEM_ASSISTANT,
                temperature=0.4,
                max_tokens=700,
            )
        except Exception as e:
            logger.warning(f"Search summary failed, formatting directly: {str(e)[:120]}")
            text = self._format_search_results(domain, results, state)
            if self.llm.frugal:
                notice = _FRUGAL_NOTICE

        return self._respond(
            state, ResponseStatus.COMPLETED, text, intent=intent,
            validation=ConstraintResult(valid=True, violations=[], warnings=warnings),
            results=results[:8], results_domain=domain, notice=notice,
        )

    # ── Group cost estimates for stays and dining ────────────────

    @staticmethod
    def _price_level_of(domain: str, rec: Dict[str, Any], preferred: Optional[str]) -> str:
        """cheap / moderate / expensive for a record, from whatever the data carries."""
        if rec.get("pricerange") in ("cheap", "moderate", "expensive"):
            return rec["pricerange"]
        kind = str(rec.get("type") or "").lower()
        if domain == "hotel":
            try:
                stars = int(str(rec.get("stars") or "0")[:1])
            except ValueError:
                stars = 0
            if stars >= 4 or kind == "resort":
                return "expensive"
            if stars == 3:
                return "moderate"
            if stars in (1, 2) or kind in ("hostel", "guest house", "guesthouse", "motel"):
                return "cheap"
        if domain == "restaurant" and kind in ("fast food", "cafe", "food court"):
            return "cheap"
        return preferred or "moderate"

    @staticmethod
    def _level_for_budget(state: PlanState) -> str:
        """
        Price level each traveller's share of the budget can afford per day
        (two meals plus half a room). No budget → moderate.
        """
        if state.budget is None:
            return "moderate"
        travelers = money.clamp_travelers(state.travelers or 1)
        days = max(state.duration_days or 1, 1)
        per_person_day = state.budget / travelers / days
        currency = state.currency

        def daily(level: str) -> float:
            return money.estimate_meal_cost(level, currency) * 2 + money.estimate_hotel_cost(level, currency) / 2

        if per_person_day >= daily("expensive"):
            return "expensive"
        if per_person_day >= daily("moderate"):
            return "moderate"
        return "cheap"

    def _stay_nights(self, state: PlanState) -> int:
        return max((state.duration_days or 2) - 1, 1)

    def _annotate_group_costs(
        self, domain: str, results: List[Dict[str, Any]], state: PlanState
    ) -> List[Dict[str, Any]]:
        """
        Add an estimated cost for the whole group (and each person's share) to
        hotel and restaurant results, check it against the group budget, and
        put affordable options first.
        """
        if domain not in ("hotel", "restaurant") or not results:
            return results

        currency = state.currency
        travelers = money.clamp_travelers(state.travelers or 1)
        preferred = tool_common.price_level(None, state.preferences) or (
            self._level_for_budget(state) if state.budget is not None else None
        )
        fmt = lambda v: money.format_money(v, currency)  # noqa: E731

        for rec in results:
            level = self._price_level_of(domain, rec, preferred)
            if domain == "hotel":
                rooms = money.rooms_needed(travelers)
                nights = self._stay_nights(state)
                per_room = money.estimate_hotel_cost(level, currency)
                group_total = per_room * rooms * nights
                text = f"≈ {fmt(per_room)}/room/night"
                if travelers > 1 or nights > 1:
                    text += (f" · {rooms} room{'s' if rooms > 1 else ''} × {nights} night"
                             f"{'s' if nights > 1 else ''} ≈ {fmt(group_total)}")
                if travelers > 1:
                    text += f" ({fmt(group_total / travelers)} each)"
            else:
                per_person = money.estimate_meal_cost(level, currency)
                group_total = per_person * travelers
                text = f"≈ {fmt(per_person)} per person"
                if travelers > 1:
                    text += f" · ≈ {fmt(group_total)} for {travelers}"

            rec["price_level"] = level
            rec["est_group_cost"] = round(group_total, 2)
            rec["est_cost_per_person"] = round(group_total / travelers, 2)
            rec["est_cost"] = text
            if state.budget is not None:
                rec["within_budget"] = group_total <= state.budget

        if state.budget is not None:
            # affordable options first, cheapest group cost breaking ties in the over-budget tail
            results.sort(key=lambda r: (not r.get("within_budget", True),
                                        r["est_group_cost"] if not r.get("within_budget", True) else 0))
        return results

    def _group_search_header(self, domain: str, state: PlanState) -> Optional[str]:
        """One line explaining how the estimates were worked out."""
        travelers = money.clamp_travelers(state.travelers or 1)
        parts = []
        if domain == "hotel":
            rooms = money.rooms_needed(travelers)
            nights = self._stay_nights(state)
            if travelers > 1:
                parts.append(f"{travelers} travellers need about {rooms} room{'s' if rooms > 1 else ''} "
                             f"(2 per room)")
            parts.append(f"{nights} night{'s' if nights > 1 else ''}")
        elif domain == "restaurant" and travelers > 1:
            parts.append(f"meal costs for {travelers} travellers")
        else:
            return None
        line = "👥 " + " · ".join(parts)
        if state.budget is not None:
            line += (f" · group budget {money.format_money(state.budget, state.currency)}"
                     + (f" ({money.format_money(state.budget / travelers, state.currency)} each)"
                        if travelers > 1 else ""))
        return line + ". Prices are rough estimates by category, not live rates."

    def _format_search_results(
        self, domain: str, results: List[dict], state: Optional[PlanState] = None
    ) -> str:
        """Deterministic formatting for single-domain search results."""
        domain_emoji = {"hotel": "🏨", "restaurant": "🍽️", "attraction": "🎯", "transport": "🚆"}
        labels = {
            "hotel": "places to stay", "restaurant": "places to eat",
            "attraction": "things to see", "transport": "transport options",
        }
        where = f" in {state.location}" if state and state.location else ""
        lines = [f"{domain_emoji.get(domain, '📋')} **Top {labels.get(domain, domain)}{where}:**\n"]

        for i, rec in enumerate(results[:8], 1):
            parts = []
            if rec.get("type"):
                parts.append(str(rec["type"]))
            if rec.get("food"):
                parts.append(str(rec["food"]))
            if rec.get("stars"):
                parts.append(f"{rec['stars']}★")
            if rec.get("pricerange"):
                parts.append(str(rec["pricerange"]))
            if rec.get("vegetarian"):
                parts.append("vegetarian-friendly")
            if rec.get("entrance_fee"):
                parts.append(f"entry: {rec['entrance_fee']}")
            if rec.get("departure") and rec.get("destination"):
                parts.append(f"{rec['departure']} → {rec['destination']}")
            if rec.get("leaveAt") or rec.get("leave_at"):
                parts.append(f"departs {rec.get('leaveAt') or rec.get('leave_at')}")
            city = (state.place or {}).get("name") if state else None
            if rec.get("area") and rec.get("area") != city:
                parts.append(str(rec["area"]))
            if rec.get("price"):
                parts.append(str(rec["price"]))
            if rec.get("distance_km") is not None:
                parts.append(f"{rec['distance_km']} km from centre")
            name = rec.get("name") or rec.get("trainID") or rec.get("train_id") or "Option"
            line = f"{i}. **{name}** - {', '.join(parts) if parts else 'details on the map'}"
            if rec.get("est_cost"):
                line += f" - 💰 {rec['est_cost']}"
                if rec.get("within_budget") is False:
                    line += " (over budget)"
            lines.append(line)

        header = self._group_search_header(domain, state) if state else None
        if header:
            lines.append(f"\n{header}")
        source = self._data_source_label(state) if state else "verified data"
        lines.append(f"\n_Source: {source}_")
        return "\n".join(lines)

    # ════════════════════════════════════════════════════════════
    # Planning
    # ════════════════════════════════════════════════════════════

    def _plan_and_respond(
        self,
        state: PlanState,
        intent: Optional[IntentResult],
        extra_warnings: List[str],
        candidate_plan: Optional[Plan] = None,
    ) -> AgentResponse:
        """PLANNING → VALIDATING → (REPLANNING) → VERIFYING → COMPLETED."""
        notice = None
        if candidate_plan is None:
            state = self.state_manager.set_status(state, AgentStatus.PLANNING)
            candidate_plan = self._generate_plan(state)

        if candidate_plan is None:
            state = self.state_manager.set_status(state, AgentStatus.ERROR)
            return self._respond(
                state,
                ResponseStatus.ERROR,
                "I wasn't able to generate a plan this time - the AI model didn't respond and "
                "there wasn't enough live data to build one without it. Please try again in a "
                "moment, or try a larger nearby destination.",
                intent=intent,
                notice=_FRUGAL_NOTICE if self.llm.frugal else None,
            )

        candidate_plan = self._finalize_plan(candidate_plan, state)

        # ─── VALIDATING (+ REPLANNING) ───────────────────────────
        state = self.state_manager.set_status(state, AgentStatus.VALIDATING)
        validation = validate_plan(candidate_plan, state)

        attempts = 0
        while not validation.valid and attempts < MAX_REPLAN_ATTEMPTS:
            attempts += 1
            state = self.state_manager.set_status(state, AgentStatus.REPLANNING)
            state = self.state_manager.set_violations(state, validation.violations)
            logger.info(f"Replanning attempt {attempts}: {validation.violations}")

            revised = self._repair_plan(candidate_plan, state, validation.violations, use_llm=(attempts == 1))
            if revised is None:
                break
            candidate_plan = self._finalize_plan(revised, state)
            validation = validate_plan(candidate_plan, state)

        if not validation.valid:
            msg = self._explain_constraint_failure(state, validation)
            return self._respond(
                state, ResponseStatus.CONSTRAINT_FAILURE, msg, intent=intent,
                validation=validation, plan=candidate_plan,
            )
        state = self.state_manager.set_violations(state, [])

        # ─── VERIFYING ───────────────────────────────────────────
        state = self.state_manager.set_status(state, AgentStatus.VERIFYING)
        verification = verify_plan(candidate_plan, state)

        # ─── COMPLETED ───────────────────────────────────────────
        state = self.state_manager.set_status(state, AgentStatus.COMPLETED)
        state = self.state_manager.update_plan(state, candidate_plan)

        if not candidate_plan.summary and self.llm.frugal:
            notice = _FRUGAL_NOTICE  # plan was built from data without AI wording

        warnings: List[str] = []
        for w in validation.warnings + verification.warnings + list(extra_warnings):
            if w not in warnings:
                warnings.append(w)

        return self._respond(
            state, ResponseStatus.COMPLETED, self._format_plan_text(candidate_plan, state),
            intent=intent, plan=candidate_plan,
            validation=ConstraintResult(valid=True, violations=[], warnings=warnings),
            notice=notice,
        )

    def _generate_plan(self, state: PlanState) -> Optional[Plan]:
        """PLANNING state: ask the LLM for a candidate plan."""
        state_summary = self.state_manager.get_state_summary(state)
        constraints_summary = self._build_constraints_summary(state)

        if state.intent in SCHEDULE_INTENTS:
            prompt = prompts.study_schedule_prompt(state_summary, constraints_summary)
        else:
            prompt = prompts.schedule_prompt(
                state_summary,
                self.state_manager.get_retrieved_options_summary(state),
                constraints_summary,
                state.currency or "USD",
                self._data_source_label(state),
            )

        try:
            plan = self.llm.generate_structured(
                prompt=prompt,
                schema=Plan,
                system="You are a schedule generation system. Respond with JSON only.",
                temperature=0.3,
            )
            if not plan.days:
                raise RuntimeError("LLM returned a plan without days")
            logger.info(f"Plan generated: {len(plan.days)} days")
            return plan
        except Exception as e:
            logger.warning(f"LLM plan generation failed, building without it: {str(e)[:160]}")
            if state.intent in SCHEDULE_INTENTS:
                return self._fallback_study_plan(state)
            return self._fallback_plan(state)

    def _repair_plan(
        self, plan: Plan, state: PlanState, violations: List[str], use_llm: bool
    ) -> Optional[Plan]:
        """REPLANNING state: fix violations - LLM first, deterministic repair second."""
        if use_llm and not self.llm.frugal:
            prompt = prompts.replanning_prompt(
                self.state_manager.get_state_summary(state) + "\n" + self._build_constraints_summary(state),
                plan.model_dump_json(exclude_none=True),
                "\n".join(f"- {v}" for v in violations),
                self.state_manager.get_retrieved_options_summary(state),
                state.currency or "USD",
            )
            try:
                revised = self.llm.generate_structured(
                    prompt=prompt,
                    schema=Plan,
                    system="You are a replanning system. Fix the problems. JSON only.",
                    temperature=0.2,
                )
                if revised.days:
                    return revised
            except Exception as e:
                logger.warning(f"LLM replanning failed: {str(e)[:120]}")

        return self._repair_deterministically(plan, state)

    def _repair_deterministically(self, plan: Plan, state: PlanState) -> Optional[Plan]:
        """Fix day count and budget overruns without the LLM."""
        plan = plan.model_copy(deep=True)
        wanted = state.duration_days

        # Day count
        if wanted and len(plan.days) > wanted:
            plan.days = plan.days[:wanted]
        elif wanted and len(plan.days) < wanted:
            filler = self._fallback_plan(state)
            if filler is not None:
                used = {a.name.lower() for d in plan.days for s in d.slots for a in s.activities}
                for extra in filler.days[len(plan.days):wanted]:
                    for slot in extra.slots:
                        slot.activities = [a for a in slot.activities if a.name.lower() not in used]
                    plan.days.append(extra)
            while len(plan.days) < wanted:
                plan.days.append(PlanDay(day=len(plan.days) + 1, slots=[
                    PlanTimeSlot(time_of_day="morning", activities=[
                        PlanActivity(name="Free time to explore at your own pace", type="activity",
                                     estimated_cost=0, details={"source": "placeholder"})
                    ]),
                    PlanTimeSlot(time_of_day="afternoon"),
                    PlanTimeSlot(time_of_day="evening"),
                ]))

        # Budget: drop the most expensive removable activities first
        if state.budget is not None:
            travelers = state.travelers or 1

            def total() -> float:
                # the budget is for the whole group, so compare group costs
                return sum(
                    money.group_cost(a.type, a.estimated_cost, travelers)
                    for d in plan.days for s in d.slots for a in s.activities
                )

            removed: List[str] = []
            guard = 0
            while total() > state.budget and guard < 60:
                guard += 1
                candidates = []
                for day in plan.days:
                    day_count = sum(len(s.activities) for s in day.slots)
                    for slot in day.slots:
                        for activity in slot.activities:
                            if (activity.estimated_cost or 0) > 0 and day_count > 1:
                                candidates.append((
                                    money.group_cost(activity.type, activity.estimated_cost, travelers),
                                    day, slot, activity,
                                ))
                if not candidates:
                    break
                _, _, slot, activity = max(candidates, key=lambda c: c[0])
                slot.activities.remove(activity)
                removed.append(activity.name)
            if removed:
                plan.assumptions.append(
                    "Removed to fit the budget: " + ", ".join(removed[:6])
                    + ("..." if len(removed) > 6 else "")
                )
        return plan

    def _finalize_plan(self, plan: Plan, state: PlanState) -> Plan:
        """Make the plan exact: numbering, dates, grounding details, totals."""
        # Index retrieved records by name for grounding
        records: Dict[str, Dict[str, Any]] = {}
        for domain, recs in state.chosen_options.items():
            for rec in recs:
                if rec.get("name"):
                    records[str(rec["name"]).lower().strip()] = {**rec, "_domain": domain}

        is_trip = state.intent not in SCHEDULE_INTENTS
        start = date.fromisoformat(state.start_date) if state.start_date else None

        days: List[PlanDay] = []
        for index, day in enumerate(sorted(plan.days, key=lambda d: d.day), start=1):
            by_slot: Dict[str, List[PlanActivity]] = {name: [] for name in SLOT_ORDER}
            for slot in day.slots:
                key = slot.time_of_day if slot.time_of_day in SLOT_ORDER else (
                    "evening" if "night" in slot.time_of_day or "dinner" in slot.time_of_day
                    else "afternoon" if "noon" in slot.time_of_day or "lunch" in slot.time_of_day
                    else "morning"
                )
                by_slot[key].extend(slot.activities)

            slots = []
            for name in SLOT_ORDER:
                activities = []
                for activity in by_slot[name]:
                    if not activity.name or not activity.name.strip():
                        continue
                    activity.name = activity.name.strip()
                    match = records.get(activity.name.lower())
                    if match is None:
                        match = next(
                            (r for key, r in records.items()
                             if len(key) > 4 and (key in activity.name.lower() or activity.name.lower() in key)),
                            None,
                        )
                    if match is not None:
                        grounded = {
                            k: match[k] for k in (
                                "address", "area", "lat", "lon", "map_url", "website", "phone",
                                "opening_hours", "food", "stars", "pricerange", "entrance_fee",
                                "distance_km", "source",
                            ) if match.get(k) not in (None, "")
                        }
                        note = activity.details.get("note") or activity.details.get("description")
                        activity.details = {**grounded, **({"note": note} if note else {})}
                        if activity.type in ("activity", ""):
                            activity.type = match["_domain"]
                    elif is_trip and activity.type in ("attraction", "restaurant", "hotel"):
                        activity.details.setdefault("source", "ai_suggested")
                    if activity.estimated_cost is not None and activity.estimated_cost < 0:
                        activity.estimated_cost = None
                    activities.append(activity)
                activities.sort(key=lambda a: a.start_time or "99:99")
                slots.append(PlanTimeSlot(time_of_day=name, activities=activities))

            days.append(PlanDay(
                day=index,
                date=(start + timedelta(days=index - 1)).isoformat() if start else None,
                slots=slots,
            ))

        plan.days = days
        plan.duration_days = len(days) or 1
        if is_trip:
            plan.location = state.location or plan.location
            plan.currency = state.currency or plan.currency
            plan.plan_type = "trip"
            # Activity costs are per person (hotels: per room per night); the
            # total is what the whole group pays, split evenly per person.
            travelers = money.clamp_travelers(state.travelers or 1)
            priced = [
                a for d in days for s in d.slots for a in s.activities
                if a.estimated_cost is not None and a.details.get("source") != "placeholder"
            ]
            plan.travelers = travelers
            plan.rooms = money.rooms_needed(travelers) if any(a.type == "hotel" for a in priced) else None
            if priced:
                plan.estimated_total_cost = float(sum(
                    money.group_cost(a.type, a.estimated_cost, travelers) for a in priced
                ))
                plan.cost_per_person = money.split_evenly(plan.estimated_total_cost, travelers)
            else:
                plan.estimated_total_cost = None
                plan.cost_per_person = None
        else:
            plan.plan_type = "study"
            plan.estimated_total_cost = None
            plan.cost_per_person = None
            plan.rooms = None
        plan.start_date = state.start_date
        plan.end_date = days[-1].date if days and days[-1].date else state.end_date
        return plan

    @staticmethod
    def _extract_subjects(goal: str) -> List[str]:
        """Subjects/topics named in a study request ("... for maths and physics")."""
        match = re.search(
            r"\b(?:for|on|covering|about)\s+"
            r"(?!\d)(.+?)(?=\s+(?:with|in|over|across|within|before|for\s+\d|during|every|each|per)\b|[.!?]|$)",
            goal, re.IGNORECASE,
        )
        if not match:
            return []
        raw = re.sub(r"\b(my|the|an?|upcoming|exams?|tests?|subjects?|schedule|plan)\b", " ", match.group(1),
                     flags=re.IGNORECASE)
        parts = [p.strip(" .") for p in re.split(r",|\band\b|&|/|\+", raw)]
        return [p.title() for p in parts if 2 <= len(p) <= 40][:6]

    def _fallback_study_plan(self, state: PlanState) -> Plan:
        """A balanced study timetable built without the LLM."""
        subjects = self._extract_subjects(state.goal or "") or ["Core topic", "Practice problems"]
        duration = state.duration_days or 3
        blocks = [
            ("morning", "09:00", 90, "Learn new material while you are fresh"),
            ("morning", "11:00", 60, "Work through practice questions"),
            ("afternoon", "14:00", 90, "Deep-focus session on the harder topics"),
            ("afternoon", "16:00", 45, "Summarise notes and make flashcards"),
            ("evening", "19:00", 45, "Light review of everything covered today"),
        ]
        days = []
        cursor = 0
        for day_num in range(1, duration + 1):
            slots: Dict[str, List[PlanActivity]] = {name: [] for name in SLOT_ORDER}
            for slot, start, minutes, note in blocks:
                subject = subjects[cursor % len(subjects)]
                cursor += 1
                slots[slot].append(PlanActivity(
                    name=subject, type="study", start_time=start,
                    duration_minutes=minutes, details={"note": note},
                ))
            slots["morning"].insert(1, PlanActivity(
                name="Short break", type="break", start_time="10:30", duration_minutes=30,
                details={"note": "Stretch, hydrate, step away from the desk"},
            ))
            slots["afternoon"].insert(1, PlanActivity(
                name="Break and a walk", type="break", start_time="15:30", duration_minutes=30,
                details={"note": "Fresh air helps the next session stick"},
            ))
            days.append(PlanDay(day=day_num, slots=[
                PlanTimeSlot(time_of_day=name, activities=slots[name]) for name in SLOT_ORDER
            ]))
        return Plan(
            duration_days=duration, days=days, plan_type="study",
            assumptions=["Standard timetable built without AI wording - ask again for a tailored version"],
        )

    def _fallback_plan(self, state: PlanState) -> Optional[Plan]:
        """Build a simple plan straight from retrieved data (no LLM)."""
        if not state.chosen_options and state.tool_results:
            for tr in state.tool_results:
                if tr.success and tr.results:
                    domain = tr.tool_name.replace("_search", "").replace("search_", "")
                    state.chosen_options[domain] = tr.results

        attractions = state.chosen_options.get("attraction", [])
        restaurants = state.chosen_options.get("restaurant", [])
        hotels = state.chosen_options.get("hotel", [])
        if not attractions and not restaurants:
            return None

        currency = state.currency
        duration = state.duration_days or 1
        level = tool_common.price_level(None, state.preferences) or self._level_for_budget(state)

        def attraction(rec: Dict[str, Any], start_time: str) -> PlanActivity:
            return PlanActivity(
                name=rec.get("name", "Attraction"), type="attraction", start_time=start_time,
                estimated_cost=self._parse_cost(rec.get("entrance_fee")),
                duration_minutes=120, details=dict(rec),
            )

        def meal(rec: Dict[str, Any], start_time: str) -> PlanActivity:
            return PlanActivity(
                name=rec.get("name", "Restaurant"), type="restaurant", start_time=start_time,
                estimated_cost=money.estimate_meal_cost(rec.get("pricerange") or level, currency),
                duration_minutes=60, details=dict(rec),
            )

        a_idx = r_idx = 0
        days = []
        for day_num in range(1, duration + 1):
            morning, afternoon, evening = [], [], []
            if a_idx < len(attractions):
                morning.append(attraction(attractions[a_idx], "09:30")); a_idx += 1
            if r_idx < len(restaurants):
                afternoon.append(meal(restaurants[r_idx], "13:00")); r_idx += 1
            if a_idx < len(attractions):
                afternoon.append(attraction(attractions[a_idx], "14:30")); a_idx += 1
            if r_idx < len(restaurants):
                evening.append(meal(restaurants[r_idx], "19:30")); r_idx += 1
            if hotels and day_num < duration:
                hotel = hotels[0]
                evening.append(PlanActivity(
                    name=hotel.get("name", "Hotel"), type="hotel", start_time="21:00",
                    estimated_cost=money.estimate_hotel_cost(hotel.get("pricerange") or level, currency),
                    details=dict(hotel),
                ))
            if not (morning or afternoon or evening):
                morning.append(PlanActivity(
                    name="Free time to explore at your own pace", type="activity",
                    estimated_cost=0, details={"source": "placeholder"},
                ))
            days.append(PlanDay(day=day_num, slots=[
                PlanTimeSlot(time_of_day="morning", activities=morning),
                PlanTimeSlot(time_of_day="afternoon", activities=afternoon),
                PlanTimeSlot(time_of_day="evening", activities=evening),
            ]))

        return Plan(
            location=state.location,
            duration_days=duration,
            days=days,
            assumptions=[
                f"Built directly from {self._data_source_label(state)} (AI wording unavailable)",
                "Meal and hotel costs are rough per-person estimates",
            ],
        )

    # ════════════════════════════════════════════════════════════
    # Replanning (user changes an existing plan)
    # ════════════════════════════════════════════════════════════

    def _handle_replanning(
        self, state: PlanState, intent: IntentResult, location_changed: bool = False
    ) -> AgentResponse:
        """Handle explicit replanning when the user modifies requirements."""
        logger.info("Handling replanning request")

        if intent.raw_changes:
            safe_changes = {k: v for k, v in intent.raw_changes.items() if k != "location"}
            state = self.state_manager.apply_changes(state, safe_changes)
        else:
            state.replan_count += 1
        self._resolve_dates(state, IntentResult(intent=intent.intent), {})

        is_trip = state.intent not in SCHEDULE_INTENTS
        if is_trip and (location_changed or not state.chosen_options):
            state.tool_results = []
            state.chosen_options = {}
            state.intent = "trip_planning"
            state = self._execute_tools(self._decompose(state), state)

        state = self.state_manager.set_status(state, AgentStatus.REPLANNING)
        warnings = check_impossible_constraints(state)

        revised: Optional[Plan] = None
        if state.current_plan is not None and not location_changed and not self.llm.frugal:
            changes = [f"User request: {state.goal}"]
            current_validation = validate_plan(state.current_plan, state)
            changes += current_validation.violations
            try:
                revised = self.llm.generate_structured(
                    prompt=prompts.replanning_prompt(
                        self.state_manager.get_state_summary(state) + "\n"
                        + self._build_constraints_summary(state),
                        state.current_plan.model_dump_json(exclude_none=True),
                        "\n".join(f"- {c}" for c in changes),
                        self.state_manager.get_retrieved_options_summary(state),
                        state.currency or "USD",
                    ),
                    schema=Plan,
                    system="You are a replanning system. Apply the requested change. JSON only.",
                    temperature=0.2,
                )
                if not revised.days:
                    revised = None
            except Exception as e:
                logger.warning(f"LLM replanning failed: {str(e)[:120]}")
                revised = None

        if revised is None and state.current_plan is not None and not location_changed:
            revised = self._repair_deterministically(state.current_plan, state)

        return self._plan_and_respond(state, intent, warnings, candidate_plan=revised)

    def replan_with_changes(self, state: PlanState, changes: Dict[str, Any]) -> AgentResponse:
        """Explicit replanning through the API (POST /replan) with structured changes."""
        description = ", ".join(f"{k} to {v}" for k, v in changes.items())
        message = f"Change {description}"
        state = self.state_manager.add_message(state, "user", message)
        state = self.state_manager.set_goal(state, message)
        intent = IntentResult(intent="replanning", is_modification=True, raw_changes=dict(changes))
        try:
            location_changed = False
            new_location = changes.get("location")
            if isinstance(new_location, str) and new_location.strip():
                place = geocoder.geocode(tool_common.strip_area_words(new_location))
                if place is not None:
                    location_changed = True
                    self._set_place(state, place)
                    self._resolve_currency(state, intent, message)
            return self._handle_replanning(state, intent, location_changed)
        except Exception as e:
            logger.error(f"Replanning failed: {e}", exc_info=True)
            return self._respond(
                state, ResponseStatus.ERROR,
                "Something went wrong while updating the plan. Please try again.",
                intent=intent,
            )

    # ════════════════════════════════════════════════════════════
    # Response building
    # ════════════════════════════════════════════════════════════

    def _respond(
        self,
        state: PlanState,
        status: ResponseStatus,
        message: str,
        intent: Optional[IntentResult] = None,
        plan: Optional[Plan] = None,
        validation: Optional[ConstraintResult] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        results_domain: Optional[str] = None,
        notice: Optional[str] = None,
    ) -> AgentResponse:
        state = self.state_manager.add_message(state, "assistant", message)
        place = state.place or {}
        context: Dict[str, Any] = {
            "location": state.location,
            "lat": place.get("lat"),
            "lon": place.get("lon"),
            "country": place.get("country"),
            "start_date": state.start_date,
            "end_date": state.end_date,
            "duration_days": state.duration_days,
            "budget": state.budget,
            "travelers": state.travelers or 1,
            "budget_per_person": money.split_evenly(state.budget, state.travelers or 1),
            "currency": state.currency,
            "currency_symbol": money.currency_symbol(state.currency).strip(),
            "data_source": self._data_source(state) if state.chosen_options else None,
            "llm_provider": self.llm.last_provider,
        }
        if notice:
            context["notice"] = notice
        return AgentResponse(
            session_id=state.session_id,
            status=status,
            message=message,
            plan=plan,
            validation=validation,
            intent=intent,
            results=results or [],
            results_domain=results_domain,
            context=context,
        )

    def _explain_constraint_failure(self, state: PlanState, validation: ConstraintResult) -> str:
        violations_str = "\n".join(f"- {v}" for v in validation.violations)
        msg = (
            "I couldn't create a plan that satisfies all of your requirements:\n\n"
            f"{violations_str}\n"
        )
        if validation.warnings:
            msg += "\nAlso worth knowing:\n" + "\n".join(f"- {w}" for w in validation.warnings) + "\n"
        msg += (
            "\nYou could try:\n"
            "- Increasing the budget\n"
            "- Reducing the number of days\n"
            "- Being more flexible with preferences\n\n"
            "The closest plan I could build is shown in the panel."
        )
        return msg

    def _format_plan_text(self, plan: Plan, state: PlanState) -> str:
        """Readable markdown for a finished plan (totals are computed, never LLM-written)."""
        currency = plan.currency or state.currency
        lines: List[str] = []

        if plan.plan_type == "study":
            title = f"📚 **Your {plan.duration_days}-day schedule**"
        else:
            title = f"📍 **{plan.duration_days}-day plan for {plan.location or 'your trip'}**"
        if plan.start_date:
            title += f" · {self._pretty_date(plan.start_date)}"
            if plan.end_date and plan.end_date != plan.start_date:
                title += f" → {self._pretty_date(plan.end_date)}"
        lines.append(title)
        if plan.summary:
            lines.append("")
            lines.append(plan.summary.strip())

        emoji = {"attraction": "🎯", "restaurant": "🍽️", "hotel": "🏨", "transport": "🚆",
                 "study": "📖", "break": "☕"}
        for day in plan.days:
            header = f"\n### Day {day.day}"
            if day.date:
                header += f" · {self._pretty_date(day.date, weekday=True)}"
            lines.append(header)
            for slot in day.slots:
                if not slot.activities:
                    continue
                lines.append(f"**{slot.time_of_day.capitalize()}**")
                for act in slot.activities:
                    bits = []
                    if act.start_time:
                        bits.append(act.start_time)
                    bits.append(f"{emoji.get(act.type, '•')} {act.name}")
                    line = "- " + " ".join(bits)
                    if act.estimated_cost and plan.travelers > 1:
                        if act.type == "hotel":
                            rooms = money.rooms_needed(plan.travelers)
                            line += (f" ({money.format_money(act.estimated_cost, currency)}/room"
                                     f" × {rooms} room{'s' if rooms > 1 else ''})")
                        else:
                            line += f" ({money.format_money(act.estimated_cost, currency)} per person)"
                    elif act.estimated_cost:
                        line += f" ({money.format_money(act.estimated_cost, currency)})"
                    elif act.estimated_cost == 0 and act.type == "attraction":
                        line += " (free)"
                    note = act.details.get("note")
                    if note:
                        line += f" - {note}"
                    lines.append(line)

        if plan.estimated_total_cost is not None and plan.travelers > 1:
            lines.append(
                f"\n💰 **Estimated total for {plan.travelers} travellers:** "
                f"{money.format_money(plan.estimated_total_cost, currency)}"
                f" · **{money.format_money(plan.cost_per_person, currency)} per person**"
            )
            if plan.rooms:
                lines.append(f"🛏️ Hotel costs assume {plan.rooms} room{'s' if plan.rooms > 1 else ''} "
                             f"(2 people per room), shared equally.")
            if state.budget:
                lines.append(
                    f"🧾 **Group budget:** {money.format_money(state.budget, currency)} "
                    f"({money.format_money(money.split_evenly(state.budget, plan.travelers), currency)} each)"
                )
        elif plan.estimated_total_cost is not None:
            budget_line = f"\n💰 **Estimated total:** {money.format_money(plan.estimated_total_cost, currency)}"
            if state.budget:
                budget_line += f" of your {money.format_money(state.budget, currency)} budget"
            lines.append(budget_line)
        if state.preferences and plan.plan_type != "study":
            lines.append(f"✅ **Preferences applied:** {', '.join(state.preferences)}")
        if plan.plan_type != "study" and state.chosen_options:
            lines.append(f"\n_Places from {self._data_source_label(state)}; costs are estimates._")
        return "\n".join(lines)

    # ════════════════════════════════════════════════════════════
    # Helpers
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _pretty_date(iso: str, weekday: bool = False) -> str:
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            return iso
        text = f"{d.day} {d.strftime('%b %Y')}"
        return f"{d.strftime('%a')}, {text}" if weekday else text

    def _build_constraints_summary(self, state: PlanState) -> str:
        parts = []
        travelers = state.travelers or 1
        if travelers > 1:
            parts.append(
                f"Group: {travelers} travellers sharing {money.rooms_needed(travelers)} hotel room(s)"
            )
        if state.budget is not None:
            if travelers > 1:
                parts.append(
                    f"Budget: {money.format_money(state.budget, state.currency)} "
                    f"({state.currency or 'currency unspecified'}) for the WHOLE group, i.e. about "
                    f"{money.format_money(money.split_evenly(state.budget, travelers), state.currency)} "
                    f"per person in total"
                )
            else:
                parts.append(
                    f"Budget: {money.format_money(state.budget, state.currency)} "
                    f"({state.currency or 'currency unspecified'}) total"
                )
        if state.duration_days is not None:
            parts.append(f"Duration: exactly {state.duration_days} day(s)")
        if state.start_date:
            dates = f"Dates: {state.start_date}"
            if state.end_date:
                dates += f" to {state.end_date}"
            try:
                dates += f" (starts on a {date.fromisoformat(state.start_date).strftime('%A')})"
            except ValueError:
                pass
            parts.append(dates)
        if state.preferences:
            parts.append(f"Preferences: {', '.join(state.preferences)}")
        if state.interests:
            parts.append(f"Interests: {', '.join(state.interests)}")
        return "\n".join(parts) if parts else "No specific constraints."

    @staticmethod
    def _parse_cost(value) -> Optional[float]:
        """Parse a cost value from various formats."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().lower()
        if text == "free":
            return 0.0
        match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def _estimate_meal_cost(pricerange: Optional[str], currency: Optional[str] = None) -> float:
        return money.estimate_meal_cost(pricerange, currency)
