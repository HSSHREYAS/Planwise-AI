"""
PlanWise AI - Planning Agent

Core agent implementing the Python state machine.
Based on Architecture doc Sections 28-29.

State machine:
    RECEIVED → UNDERSTANDING → DECOMPOSING → EXECUTING →
    PLANNING → VALIDATING → VERIFYING → COMPLETED

Branches:
    MISSING_INFORMATION → WAITING_FOR_USER
    CONSTRAINT_VIOLATION → REPLANNING → EXECUTING/PLANNING → VALIDATING
    ERROR → CONTROLLED_RECOVERY
"""

import json
import logging
from typing import List, Optional

from app.agent.prompts import (
    clarification_prompt,
    decomposition_prompt,
    intent_prompt,
    replanning_prompt,
    response_prompt,
    schedule_prompt,
    search_results_prompt,
    study_schedule_prompt,
)
from app.config import MAX_REPLAN_ATTEMPTS
from app.llm.ollama_client import OllamaClient
from app.models.schemas import (
    AgentResponse,
    AgentStatus,
    ConstraintResult,
    IntentResult,
    Plan,
    PlanState,
    ResponseStatus,
    Task,
    TaskStatus,
    ToolResult,
)
from app.state.manager import StateManager
from app.tools.registry import execute_tool
from app.validation.constraints import check_impossible_constraints, validate_plan
from app.validation.verifier import verify_plan

logger = logging.getLogger(__name__)


class PlanningAgent:
    """
    Core planning agent with explicit state machine transitions.

    The agent follows the Architecture doc's core algorithm:
    understand → check missing → decompose → execute tools →
    generate plan → validate → verify → respond
    """

    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.llm = llm_client or OllamaClient()
        self.state_manager = StateManager()

    def handle_message(
        self, message: str, state: PlanState
    ) -> AgentResponse:
        """
        Main entry point. Processes a user message through the full
        state machine and returns an AgentResponse.
        """
        logger.info(f"Processing message: '{message[:100]}...'")

        # Add user message to conversation history
        state = self.state_manager.add_message(state, "user", message)
        state = self.state_manager.set_goal(state, message)

        try:
            # ─── UNDERSTANDING ───────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.UNDERSTANDING)
            intent = self._understand(message, state)
            state = self.state_manager.update_from_intent(state, intent)

            # Check if this is a modification of existing plan
            if intent.is_modification and state.current_plan:
                return self._handle_replanning(state, intent)

            # ─── CHECK MISSING INFO ──────────────────────────────
            missing = self._check_missing_info(state)
            if missing:
                state = self.state_manager.set_status(
                    state, AgentStatus.WAITING_FOR_USER
                )
                clarification_msg = self._generate_clarification(missing, state)
                state = self.state_manager.add_message(
                    state, "assistant", clarification_msg
                )
                return AgentResponse(
                    session_id=state.session_id,
                    status=ResponseStatus.CLARIFICATION_REQUIRED,
                    message=clarification_msg,
                    intent=intent,
                )

            # Check for impossible constraints early
            impossible_warnings = check_impossible_constraints(state)

            # ─── DECOMPOSING ─────────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.DECOMPOSING)

            if state.intent in ("study_planning", "schedule_generation"):
                # Study planning doesn't need tool calls
                tasks = []
            else:
                tasks = self._decompose(state)
                state = self.state_manager.set_subtasks(state, tasks)

            # ─── EXECUTING (TOOL CALLS) ──────────────────────────
            if tasks:
                state = self.state_manager.set_status(state, AgentStatus.EXECUTING)
                state = self._execute_tools(tasks, state)

            # ─── DIRECT SEARCH RESULTS PATH ──────────────────────
            # For single-domain searches (e.g., "find me hotels"),
            # return results directly instead of forcing a schedule.
            if self._is_single_domain_search(state):
                return self._handle_search_results(state, intent, impossible_warnings)

            # ─── PLANNING ────────────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.PLANNING)
            candidate_plan = self._generate_plan(state)

            if candidate_plan is None:
                state = self.state_manager.set_status(state, AgentStatus.ERROR)
                error_msg = (
                    "I wasn't able to generate a plan. This might be due to "
                    "limited data for the requested location or preferences. "
                    "Could you try with different criteria?"
                )
                state = self.state_manager.add_message(
                    state, "assistant", error_msg
                )
                return AgentResponse(
                    session_id=state.session_id,
                    status=ResponseStatus.ERROR,
                    message=error_msg,
                    intent=intent,
                )

            # ─── VALIDATING ──────────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.VALIDATING)
            validation = validate_plan(candidate_plan, state)

            # If validation fails, attempt replanning
            replan_attempts = 0
            while not validation.valid and replan_attempts < MAX_REPLAN_ATTEMPTS:
                replan_attempts += 1
                state = self.state_manager.set_status(
                    state, AgentStatus.REPLANNING
                )
                state = self.state_manager.set_violations(
                    state, validation.violations
                )
                logger.info(
                    f"Replanning attempt {replan_attempts}: {validation.violations}"
                )
                candidate_plan = self._replan(state, validation.violations)
                if candidate_plan is None:
                    break
                validation = validate_plan(candidate_plan, state)

            # If still invalid after replanning
            if not validation.valid:
                msg = self._explain_constraint_failure(state, validation)
                state = self.state_manager.add_message(state, "assistant", msg)
                return AgentResponse(
                    session_id=state.session_id,
                    status=ResponseStatus.CONSTRAINT_FAILURE,
                    message=msg,
                    validation=validation,
                    plan=candidate_plan,
                    intent=intent,
                )

            # ─── VERIFYING ───────────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.VERIFYING)
            verification = verify_plan(candidate_plan, state)

            # Verification warnings are non-blocking but logged
            if verification.warnings:
                logger.info(f"Verification warnings: {verification.warnings}")

            # ─── COMPLETED ───────────────────────────────────────
            state = self.state_manager.set_status(state, AgentStatus.COMPLETED)
            state = self.state_manager.update_plan(state, candidate_plan)

            # Generate final response
            response_text = self._generate_response(candidate_plan, state)

            # Merge warnings from validation and verification
            all_warnings = validation.warnings + verification.warnings
            if impossible_warnings:
                all_warnings.extend(impossible_warnings)

            final_validation = ConstraintResult(
                valid=True,
                violations=[],
                warnings=all_warnings,
            )

            state = self.state_manager.add_message(
                state, "assistant", response_text
            )

            return AgentResponse(
                session_id=state.session_id,
                status=ResponseStatus.COMPLETED,
                message=response_text,
                plan=candidate_plan,
                validation=final_validation,
                intent=intent,
            )

        except ConnectionError as e:
            logger.error(f"LLM connection error: {e}")
            error_msg = (
                "I'm unable to connect to the AI model right now. "
                "Please make sure Ollama is running and try again."
            )
            return AgentResponse(
                session_id=state.session_id,
                status=ResponseStatus.ERROR,
                message=error_msg,
            )
        except Exception as e:
            logger.error(f"Unexpected agent error: {e}", exc_info=True)
            error_msg = (
                "Something went wrong while processing your request. "
                "Please try again or rephrase your request."
            )
            return AgentResponse(
                session_id=state.session_id,
                status=ResponseStatus.ERROR,
                message=error_msg,
            )

    def _handle_replanning(
        self, state: PlanState, intent: IntentResult
    ) -> AgentResponse:
        """Handle explicit replanning when user modifies requirements."""
        logger.info("Handling replanning request")

        # Apply changes from intent
        if intent.raw_changes:
            state = self.state_manager.apply_changes(state, intent.raw_changes)
        if intent.budget is not None:
            state.budget = intent.budget
        if intent.duration_days is not None:
            state.duration_days = intent.duration_days
        if intent.preferences:
            for p in intent.preferences:
                if p.lower() not in [x.lower() for x in state.preferences]:
                    state.preferences.append(p.lower())

        # May need to re-run tools if location changed
        needs_new_retrieval = (
            intent.location and intent.location != state.location
        )
        if needs_new_retrieval and intent.location:
            state.location = intent.location
            state.tool_results = []
            state.chosen_options = {}
            tasks = self._decompose(state)
            state = self._execute_tools(tasks, state)

        # Generate revised plan
        state = self.state_manager.set_status(state, AgentStatus.REPLANNING)
        candidate_plan = self._generate_plan(state)

        if candidate_plan is None:
            msg = "I couldn't generate a revised plan with the new constraints."
            state = self.state_manager.add_message(state, "assistant", msg)
            return AgentResponse(
                session_id=state.session_id,
                status=ResponseStatus.ERROR,
                message=msg,
            )

        # Validate
        validation = validate_plan(candidate_plan, state)
        replan_attempts = 0
        while not validation.valid and replan_attempts < MAX_REPLAN_ATTEMPTS:
            replan_attempts += 1
            candidate_plan = self._replan(state, validation.violations)
            if candidate_plan is None:
                break
            validation = validate_plan(candidate_plan, state)

        if not validation.valid:
            msg = self._explain_constraint_failure(state, validation)
            state = self.state_manager.add_message(state, "assistant", msg)
            return AgentResponse(
                session_id=state.session_id,
                status=ResponseStatus.CONSTRAINT_FAILURE,
                message=msg,
                validation=validation,
                plan=candidate_plan,
                intent=intent,
            )

        # Verify and complete
        verification = verify_plan(candidate_plan, state)
        state = self.state_manager.update_plan(state, candidate_plan)
        state = self.state_manager.set_status(state, AgentStatus.COMPLETED)

        response_text = self._generate_response(candidate_plan, state)
        state = self.state_manager.add_message(state, "assistant", response_text)

        return AgentResponse(
            session_id=state.session_id,
            status=ResponseStatus.COMPLETED,
            message=response_text,
            plan=candidate_plan,
            validation=ConstraintResult(
                valid=True,
                violations=[],
                warnings=validation.warnings + verification.warnings,
            ),
            intent=intent,
        )

    # ── Single-domain search helpers ─────────────────────────────

    def _is_single_domain_search(self, state: PlanState) -> bool:
        """Check if this is a single-domain search (not trip planning)."""
        return state.intent in (
            "hotel_search", "restaurant_search",
            "attraction_search", "transport_search",
        )

    def _handle_search_results(
        self, state: PlanState, intent: IntentResult, warnings: List[str]
    ) -> AgentResponse:
        """Handle single-domain search by returning results directly."""
        state = self.state_manager.set_status(state, AgentStatus.COMPLETED)

        # Gather results from tools
        all_results = []
        domain = state.intent.replace("_search", "")
        for tr in state.tool_results:
            if tr.success and tr.results:
                all_results.extend(tr.results)

        if not all_results:
            # Check chosen_options as fallback
            all_results = state.chosen_options.get(domain, [])

        if not all_results:
            msg = (
                f"I couldn't find any {domain} options matching your criteria. "
                f"The data covers Cambridge, UK. Try adjusting your preferences "
                f"or area (e.g., centre, north, south, east, west)."
            )
            state = self.state_manager.add_message(state, "assistant", msg)
            return AgentResponse(
                session_id=state.session_id,
                status=ResponseStatus.COMPLETED,
                message=msg,
                intent=intent,
            )

        # Format results using LLM or fallback
        options_summary = self.state_manager.get_retrieved_options_summary(state)
        prompt = search_results_prompt(domain, options_summary, state.goal or "")

        try:
            response_text = self.llm.generate(
                prompt=prompt,
                system="You are a helpful planning assistant. Present search results clearly.",
                temperature=0.5,
            )
        except Exception:
            # Fallback: format results directly
            response_text = self._format_search_results(domain, all_results)

        state = self.state_manager.add_message(state, "assistant", response_text)

        return AgentResponse(
            session_id=state.session_id,
            status=ResponseStatus.COMPLETED,
            message=response_text,
            intent=intent,
            validation=ConstraintResult(
                valid=True, violations=[], warnings=warnings,
            ),
        )

    def _format_search_results(
        self, domain: str, results: List[dict]
    ) -> str:
        """Fallback formatting for single-domain search results."""
        domain_emoji = {
            "hotel": "🏨", "restaurant": "🍽️",
            "attraction": "🎯", "transport": "🚂",
        }
        emoji = domain_emoji.get(domain, "📋")
        lines = [f"{emoji} **{domain.capitalize()} Options Found:**\n"]

        for i, rec in enumerate(results[:8], 1):
            name = rec.get("name", "Unknown")
            parts = []
            for key in ["area", "pricerange", "food", "type", "stars",
                        "entrance_fee", "price", "address", "phone"]:
                val = rec.get(key)
                if val:
                    parts.append(f"{key}: {val}")
            details = " | ".join(parts)
            lines.append(f"{i}. **{name}** — {details}")

        lines.append(f"\n_Data from MultiWOZ 2.2 (Cambridge, UK)_")
        return "\n".join(lines)

    # ── State Machine Steps ─────────────────────────────────────

    def _understand(self, message: str, state: PlanState) -> IntentResult:
        """UNDERSTANDING state: Extract intent and parameters."""
        conversation_summary = self.state_manager.get_conversation_summary(state)
        prompt = intent_prompt(message, conversation_summary)

        try:
            result = self.llm.generate_structured(
                prompt=prompt,
                schema=IntentResult,
                system="You are a planning intent extraction system. Respond with JSON only.",
            )
            logger.info(f"Intent extracted: {result.intent}")
            return result
        except RuntimeError:
            # Fallback: basic intent detection
            logger.warning("LLM structured output failed, using fallback intent")
            return self._fallback_intent(message, state)

    def _fallback_intent(self, message: str, state: PlanState) -> IntentResult:
        """Fallback intent detection when LLM structured output fails."""
        msg_lower = message.lower()

        intent = "general_query"
        is_mod = False

        if any(w in msg_lower for w in ["hotel", "stay", "accommodation"]):
            intent = "hotel_search"
        elif any(w in msg_lower for w in ["restaurant", "food", "eat", "dining"]):
            intent = "restaurant_search"
        elif any(w in msg_lower for w in ["attraction", "visit", "see", "place"]):
            intent = "attraction_search"
        elif any(w in msg_lower for w in ["train", "taxi", "transport", "travel"]):
            intent = "transport_search"
        elif any(w in msg_lower for w in ["study", "exam", "subject", "learn"]):
            intent = "study_planning"
        elif any(w in msg_lower for w in ["trip", "plan", "itinerary", "schedule", "day"]):
            intent = "trip_planning"

        # Check if modification
        if any(w in msg_lower for w in ["change", "reduce", "increase", "modify",
                                         "update", "instead", "actually"]):
            is_mod = state.current_plan is not None

        # Extract budget
        budget = None
        import re
        budget_match = re.search(r'[₹$]?\s*(\d[\d,]*)', message)
        if budget_match:
            budget = float(budget_match.group(1).replace(",", ""))

        # Extract duration
        duration = None
        duration_match = re.search(r'(\d+)\s*(?:day|days)', msg_lower)
        if duration_match:
            duration = int(duration_match.group(1))

        # Extract preferences
        preferences = []
        if "vegetarian" in msg_lower or "veg" in msg_lower:
            preferences.append("vegetarian")

        return IntentResult(
            intent=intent,
            budget=budget,
            duration_days=duration,
            preferences=preferences,
            is_modification=is_mod,
        )

    def _check_missing_info(self, state: PlanState) -> Optional[List[str]]:
        """Check if essential info is missing for planning/search."""
        missing = []

        # Trip planning needs both location and duration
        if state.intent == "trip_planning":
            if not state.location:
                missing.append("location/destination")
            if not state.duration_days:
                missing.append("number of days")

        # Single-domain searches need at least a location or some filter
        elif state.intent in (
            "hotel_search", "restaurant_search",
            "attraction_search", "transport_search",
        ):
            # For domain searches, location helps a lot but isn't strictly
            # required — MultiWOZ data is all Cambridge so we can default.
            # Only ask for clarification if the query is extremely vague
            # (no location AND no preferences AND no interests).
            if (
                not state.location
                and not state.preferences
                and not state.interests
                and not state.budget
            ):
                # Default to Cambridge since that's what MultiWOZ covers
                state.location = "cambridge"
                logger.info("Defaulting location to Cambridge (MultiWOZ dataset)")

        return missing if missing else None

    def _decompose(self, state: PlanState) -> List[Task]:
        """DECOMPOSING state: Break goal into subtasks."""
        state_summary = self.state_manager.get_state_summary(state)
        prompt = decomposition_prompt(state_summary)

        try:
            raw_response = self.llm.generate(
                prompt=prompt,
                system="You are a task decomposition system. Respond with JSON only.",
                temperature=0.1,
            )
            parsed = self.llm._extract_json(raw_response)
            tasks_data = parsed.get("tasks", [])
        except Exception as e:
            logger.warning(f"LLM decomposition failed, using fallback: {e}")
            tasks_data = self._fallback_decompose(state)

        # Convert to Task objects
        tasks = []
        task_type_to_tool = {
            "search_hotels": "hotel_search",
            "search_restaurants": "restaurant_search",
            "search_attractions": "attraction_search",
            "search_transport": "transport_search",
            "hotel_search": "hotel_search",
            "restaurant_search": "restaurant_search",
            "attraction_search": "attraction_search",
            "transport_search": "transport_search",
        }

        for td in tasks_data:
            task_type = td.get("task_type", td.get("type", ""))
            # Normalize task type to tool name
            tool_name = task_type_to_tool.get(task_type, task_type)
            params = td.get("parameters", {})

            # Ensure location is in params
            if state.location and "location" not in params:
                params["location"] = state.location

            tasks.append(Task(
                task_type=tool_name,
                parameters=params,
            ))

        logger.info(f"Decomposed into {len(tasks)} tasks: {[t.task_type for t in tasks]}")
        return tasks

    def _fallback_decompose(self, state: PlanState) -> List[dict]:
        """Fallback decomposition when LLM fails."""
        tasks = []

        # Default location to Cambridge if missing (MultiWOZ is Cambridge data)
        location = state.location or "cambridge"

        if state.intent in ("trip_planning", "schedule_generation"):
            tasks.append({
                "task_type": "search_attractions",
                "parameters": {"location": location, "interests": state.interests},
            })
            tasks.append({
                "task_type": "search_restaurants",
                "parameters": {
                    "location": location,
                    "preferences": state.preferences,
                },
            })
            tasks.append({
                "task_type": "search_hotels",
                "parameters": {"location": location},
            })

        elif state.intent == "hotel_search":
            tasks.append({
                "task_type": "search_hotels",
                "parameters": {"location": location},
            })

        elif state.intent == "restaurant_search":
            tasks.append({
                "task_type": "search_restaurants",
                "parameters": {
                    "location": location,
                    "preferences": state.preferences,
                },
            })

        elif state.intent == "attraction_search":
            tasks.append({
                "task_type": "search_attractions",
                "parameters": {
                    "location": location,
                    "interests": state.interests,
                },
            })

        elif state.intent == "transport_search":
            tasks.append({
                "task_type": "search_transport",
                "parameters": {"location": location},
            })

        return tasks

    def _execute_tools(
        self, tasks: List[Task], state: PlanState
    ) -> PlanState:
        """EXECUTING state: Run tools for each task."""
        # Import tools to register them
        import app.tools.hotel  # noqa: F401
        import app.tools.restaurant  # noqa: F401
        import app.tools.attraction  # noqa: F401
        import app.tools.transport  # noqa: F401

        for task in tasks:
            if task.task_type == "generate_schedule":
                task.status = TaskStatus.SKIPPED
                continue

            logger.info(f"Executing tool: {task.task_type}")
            result = execute_tool(task.task_type, task.parameters)
            task.result = result
            task.status = (
                TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            )
            state = self.state_manager.update_from_tool_result(state, result)

        return state

    def _generate_plan(self, state: PlanState) -> Optional[Plan]:
        """PLANNING state: Generate a candidate plan using LLM."""
        state_summary = self.state_manager.get_state_summary(state)
        retrieved_options = self.state_manager.get_retrieved_options_summary(state)
        constraints_summary = self._build_constraints_summary(state)

        if state.intent in ("study_planning", "schedule_generation"):
            prompt = study_schedule_prompt(state_summary, constraints_summary)
        else:
            prompt = schedule_prompt(state_summary, retrieved_options, constraints_summary)

        try:
            plan = self.llm.generate_structured(
                prompt=prompt,
                schema=Plan,
                system="You are a schedule generation system. Respond with JSON only.",
            )
            logger.info(f"Plan generated: {len(plan.days)} days")
            return plan
        except RuntimeError as e:
            logger.error(f"Plan generation failed: {e}")
            return self._fallback_plan(state)

    def _fallback_plan(self, state: PlanState) -> Optional[Plan]:
        """Create a basic plan from retrieved data when LLM fails."""
        if not state.chosen_options and not state.tool_results:
            return None

        from app.models.schemas import PlanActivity, PlanDay, PlanTimeSlot

        # Rebuild chosen_options from tool_results if empty
        if not state.chosen_options and state.tool_results:
            for tr in state.tool_results:
                if tr.success and tr.results:
                    domain = tr.tool_name.replace("_search", "").replace("search_", "")
                    state.chosen_options[domain] = tr.results

        if not state.chosen_options:
            return None

        days = []
        duration = state.duration_days or 1

        # Gather all available options
        attractions = state.chosen_options.get("attraction", [])
        restaurants = state.chosen_options.get("restaurant", [])
        hotels = state.chosen_options.get("hotel", [])

        attraction_idx = 0
        restaurant_idx = 0

        for day_num in range(1, duration + 1):
            slots = []
            for time_slot in ["morning", "afternoon", "evening"]:
                activities = []
                if time_slot in ("morning", "afternoon") and attraction_idx < len(attractions):
                    att = attractions[attraction_idx]
                    activities.append(PlanActivity(
                        name=att.get("name", "Unknown Attraction"),
                        type="attraction",
                        estimated_cost=self._parse_cost(att.get("entrance_fee")),
                        details=att,
                    ))
                    attraction_idx += 1
                if time_slot in ("afternoon", "evening") and restaurant_idx < len(restaurants):
                    rest = restaurants[restaurant_idx]
                    activities.append(PlanActivity(
                        name=rest.get("name", "Unknown Restaurant"),
                        type="restaurant",
                        estimated_cost=self._estimate_meal_cost(rest.get("pricerange")),
                        details=rest,
                    ))
                    restaurant_idx += 1

                # Add hotel info on first day morning if available
                if day_num == 1 and time_slot == "morning" and hotels:
                    hotel = hotels[0]
                    activities.append(PlanActivity(
                        name=hotel.get("name", "Unknown Hotel"),
                        type="hotel",
                        estimated_cost=self._estimate_meal_cost(hotel.get("pricerange")),
                        details=hotel,
                    ))

                slots.append(PlanTimeSlot(time_of_day=time_slot, activities=activities))
            days.append(PlanDay(day=day_num, slots=slots))

        total_cost = sum(
            a.estimated_cost or 0
            for d in days for s in d.slots for a in s.activities
        )

        return Plan(
            location=state.location or "Cambridge",
            duration_days=duration,
            days=days,
            estimated_total_cost=total_cost if total_cost > 0 else None,
            assumptions=["Plan generated from available MultiWOZ data", "All locations are in Cambridge, UK"],
        )

    def _replan(
        self, state: PlanState, violations: List[str]
    ) -> Optional[Plan]:
        """REPLANNING state: Revise plan to fix violations."""
        state_summary = self.state_manager.get_state_summary(state)
        retrieved_options = self.state_manager.get_retrieved_options_summary(state)
        current_plan_summary = ""
        if state.current_plan:
            current_plan_summary = state.current_plan.model_dump_json(indent=2)
        violations_str = "\n".join(f"- {v}" for v in violations)

        prompt = replanning_prompt(
            state_summary, current_plan_summary, violations_str, retrieved_options
        )

        try:
            plan = self.llm.generate_structured(
                prompt=prompt,
                schema=Plan,
                system="You are a replanning system. Fix the violations. JSON only.",
            )
            return plan
        except RuntimeError:
            logger.warning("LLM replanning failed, using fallback")
            return self._fallback_plan(state)

    def _generate_response(self, plan: Plan, state: PlanState) -> str:
        """COMPLETED state: Generate natural language response."""
        plan_summary = plan.model_dump_json(indent=2)
        state_summary = self.state_manager.get_state_summary(state)
        prompt = response_prompt(plan_summary, state_summary)

        try:
            response = self.llm.generate(
                prompt=prompt,
                system="You are a helpful planning assistant. Create a clear, readable summary.",
                temperature=0.5,
            )
            return response
        except Exception:
            # Fallback: format plan directly
            return self._format_plan_text(plan, state)

    def _generate_clarification(
        self, missing: List[str], state: PlanState
    ) -> str:
        """Generate a clarification message."""
        state_summary = self.state_manager.get_state_summary(state)
        prompt = clarification_prompt(missing, state_summary)

        try:
            return self.llm.generate(prompt=prompt, temperature=0.5)
        except Exception:
            fields = ", ".join(missing)
            return f"I need a few more details to create your plan. Could you provide: {fields}?"

    def _explain_constraint_failure(
        self, state: PlanState, validation: ConstraintResult
    ) -> str:
        """Explain why constraints couldn't be satisfied."""
        violations_str = "\n".join(f"• {v}" for v in validation.violations)
        warnings_str = "\n".join(f"• {w}" for w in validation.warnings) if validation.warnings else ""

        msg = (
            "I wasn't able to create a plan that satisfies all your requirements:\n\n"
            f"{violations_str}\n"
        )
        if warnings_str:
            msg += f"\nAdditional notes:\n{warnings_str}\n"
        msg += (
            "\nYou could try:\n"
            "- Increasing the budget\n"
            "- Reducing the number of days\n"
            "- Being more flexible with preferences"
        )
        return msg

    def _format_plan_text(self, plan: Plan, state: PlanState) -> str:
        """Fallback plan formatting when LLM response generation fails."""
        lines = []
        if plan.location:
            lines.append(f"📍 **Plan for {plan.location}** ({plan.duration_days} day(s))\n")

        for day in plan.days:
            lines.append(f"\n**Day {day.day}**")
            for slot in day.slots:
                lines.append(f"  {slot.time_of_day.capitalize()}:")
                if slot.activities:
                    for act in slot.activities:
                        cost_str = f" (₹{act.estimated_cost:.0f})" if act.estimated_cost else ""
                        lines.append(f"    • {act.name}{cost_str}")
                else:
                    lines.append("    • Free time")

        if plan.estimated_total_cost is not None:
            budget_str = f"\n💰 **Estimated total**: ₹{plan.estimated_total_cost:.0f}"
            if state.budget:
                budget_str += f" / ₹{state.budget:.0f} budget"
            lines.append(budget_str)

        if state.preferences:
            lines.append(f"\n✅ **Preferences applied**: {', '.join(state.preferences)}")

        return "\n".join(lines)

    # ── Helpers ──────────────────────────────────────────────────

    def _build_constraints_summary(self, state: PlanState) -> str:
        """Build constraints text for prompts."""
        parts = []
        if state.budget is not None:
            parts.append(f"Budget: ₹{state.budget:.0f}")
        if state.duration_days is not None:
            parts.append(f"Duration: {state.duration_days} day(s)")
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
        try:
            cleaned = str(value).replace("£", "").replace("$", "").replace("₹", "").replace(",", "").strip()
            if cleaned and cleaned.lower() not in ("free", "?", "unknown", ""):
                return float(cleaned)
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _estimate_meal_cost(pricerange: Optional[str]) -> Optional[float]:
        """Estimate meal cost from MultiWOZ pricerange."""
        mapping = {
            "cheap": 200.0,
            "moderate": 500.0,
            "expensive": 1000.0,
        }
        if pricerange:
            return mapping.get(pricerange.lower(), 400.0)
        return 400.0
