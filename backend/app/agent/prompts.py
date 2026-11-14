"""
PlanWise AI - Prompt Templates

All LLM prompt templates, separated from Python logic.

Each prompt clearly specifies:
- Role the model is performing
- State/data it receives
- Expected output schema
- Grounding rules (what may and may not be invented)
"""

from datetime import date
from typing import List, Optional

SYSTEM_ASSISTANT = (
    "You are PlanWise AI, a friendly and precise trip and task planning assistant. "
    "You are grounded in live map data supplied by the application. "
    "Be concise, concrete and honest about what is verified and what is a suggestion."
)


def intent_prompt(message: str, conversation_summary: str = "", today: Optional[date] = None) -> str:
    """Prompt for understanding user intent and extracting parameters."""
    today = today or date.today()
    context_section = ""
    if conversation_summary:
        context_section = f"""
CONVERSATION CONTEXT (previous state):
{conversation_summary}
"""

    return f"""You are PlanWise AI's intent understanding module.

Analyze the user's message and extract their planning intent.
Today's date is {today.isoformat()} ({today.strftime('%A')}).
{context_section}
USER MESSAGE: "{message}"

Respond with ONLY a JSON object (no markdown, no explanation) with these fields:
{{
    "intent": "<one of: trip_planning, hotel_search, restaurant_search, attraction_search, transport_search, study_planning, schedule_generation, replanning, general_query>",
    "location": "<city/place named in THIS message, or null>",
    "duration_days": <number or null>,
    "start_date": "<YYYY-MM-DD or null>",
    "end_date": "<YYYY-MM-DD or null>",
    "budget": <number or null>,
    "currency": "<ISO code such as INR, USD, GBP, EUR if the user named a currency, else null>",
    "preferences": ["<food / stay / style preferences like vegetarian, cheap, luxury, wifi, italian>"],
    "interests": ["<interests like museums, history, nature, temples, shopping>"],
    "is_modification": <true if the user is changing an existing plan, false otherwise>,
    "raw_changes": {{"<field>": "<new_value>"}} or null
}}

RULES:
- "location" must be a real place name the user wrote in this message. Use null for
  phrases like "near me", "nearby", "here" or when no place is named.
- Resolve relative dates ("tomorrow", "next Friday", "this weekend") against today's date.
- Building a multi-activity itinerary or day plan = trip_planning. Looking for one kind of
  place = the matching *_search intent. Greetings, travel advice and anything else = general_query.
- If the user changes budget, duration, dates or preferences of an existing plan, set
  is_modification=true and fill raw_changes.
- If something is not mentioned, use null or an empty list.
- Do NOT invent information the user did not provide.
- Respond with ONLY the JSON object."""


def schedule_prompt(
    state_summary: str,
    retrieved_options: str,
    constraints_summary: str,
    currency: str,
    data_source: str,
) -> str:
    """Prompt for generating a candidate schedule/plan."""
    return f"""You are PlanWise AI's schedule generation module.

Generate a structured day-by-day trip plan.

CURRENT STATE:
{state_summary}

CONSTRAINTS:
{constraints_summary}

AVAILABLE OPTIONS ({data_source}):
{retrieved_options}

Respond with ONLY a JSON object:
{{
    "summary": "<2-3 friendly sentences introducing the plan and its highlights>",
    "location": "<destination>",
    "duration_days": <number>,
    "days": [
        {{
            "day": 1,
            "slots": [
                {{
                    "time_of_day": "morning",
                    "activities": [
                        {{
                            "name": "<place name>",
                            "type": "<attraction | restaurant | hotel | transport | activity>",
                            "start_time": "<HH:MM 24h>",
                            "estimated_cost": <typical cost per person in {currency}, 0 if free>,
                            "duration_minutes": <number>,
                            "details": {{"note": "<one short practical tip>"}}
                        }}
                    ]
                }},
                {{"time_of_day": "afternoon", "activities": [...]}},
                {{"time_of_day": "evening", "activities": [...]}}
            ]
        }}
    ],
    "assumptions": ["<any assumptions made>"],
    "plan_type": "trip"
}}

RULES:
- Build the plan from the AVAILABLE OPTIONS and copy their names exactly.
- You may add a FEW iconic, world-famous landmarks or experiences of the destination
  that are missing from the list. Mark each of those with "details": {{"source": "ai_suggested", ...}}.
- If a category has no options listed, you may suggest well-known real places for it,
  again marked with "source": "ai_suggested". Never invent fictional places.
- Every day needs morning, afternoon and evening slots with at least one activity per day.
  Include lunch and dinner at restaurants. Group nearby places on the same day.
- Do not repeat the same attraction or restaurant on different days.
- For multi-day trips with hotel options, add the chosen hotel as a "hotel" activity in the
  evening slot of every day except the last, with its per-night cost.
- All costs are realistic per-person estimates in {currency}. Respect every constraint,
  and keep the sum of all costs within the budget when one is given.
- Honor dietary preferences in every restaurant choice.
- Keep "details" small. Respond with ONLY the JSON object."""


def study_schedule_prompt(state_summary: str, constraints_summary: str) -> str:
    """Prompt for generating a study/personal schedule."""
    return f"""You are PlanWise AI's study schedule generation module.

Generate a structured study / personal schedule based on the user's requirements.

CURRENT STATE:
{state_summary}

CONSTRAINTS:
{constraints_summary}

Respond with ONLY a JSON object:
{{
    "summary": "<2-3 encouraging sentences describing the schedule>",
    "location": null,
    "duration_days": <number>,
    "days": [
        {{
            "day": 1,
            "slots": [
                {{
                    "time_of_day": "morning",
                    "activities": [
                        {{
                            "name": "<study topic / task>",
                            "type": "study",
                            "start_time": "<HH:MM 24h>",
                            "estimated_cost": null,
                            "duration_minutes": <number>,
                            "details": {{"note": "<what to focus on>"}}
                        }}
                    ]
                }},
                {{"time_of_day": "afternoon", "activities": [...]}},
                {{"time_of_day": "evening", "activities": [...]}}
            ]
        }}
    ],
    "assumptions": ["<any assumptions made>"],
    "plan_type": "study"
}}

RULES:
- Create a realistic, balanced schedule with breaks ("type": "break") and variety.
- Respect any time constraints, subjects and deadlines the user mentioned.
- If no duration is given, plan for a sensible number of days (1 to 7).
- Respond with ONLY the JSON object."""


def replanning_prompt(
    state_summary: str,
    current_plan_summary: str,
    violations: str,
    retrieved_options: str,
    currency: str,
) -> str:
    """Prompt for revising an existing plan after constraint changes."""
    return f"""You are PlanWise AI's replanning module.

Revise the current plan so that it satisfies the updated requirements and fixes the
listed problems, while preserving as much of the existing plan as possible.

CURRENT STATE (latest requirements):
{state_summary}

CURRENT PLAN:
{current_plan_summary}

PROBLEMS TO FIX:
{violations}

AVAILABLE OPTIONS:
{retrieved_options}

Respond with ONLY a JSON object with the same structure as the current plan
(summary, location, duration_days, days → slots → activities, assumptions, plan_type).

RULES:
- Fix ALL listed problems.
- The number of days must equal the requested duration exactly.
- Prefer cheaper alternatives or remove optional activities if budget is the issue.
- Costs are per-person estimates in {currency}.
- Prefer names from the available options; mark anything else with
  "details": {{"source": "ai_suggested"}}.
- Respond with ONLY the JSON object."""


def search_results_prompt(
    domain: str,
    options_summary: str,
    user_goal: str,
    location: str,
    constraints_summary: str,
) -> str:
    """Prompt for presenting single-domain search results."""
    return f"""The user is looking for {domain} options in {location}.

USER REQUEST: "{user_goal}"

USER CONSTRAINTS:
{constraints_summary}

VERIFIED RESULTS (live data - use ONLY these places):
{options_summary}

Write a short, helpful answer in markdown:
1. One sentence acknowledging the request and the location.
2. A numbered list of the best matching options (at most 6). For each: **Name** in bold,
   then a dash and one line with the most useful facts from the data
   (type / cuisine, area, distance from the centre, stars, entry fee, opening hours).
3. End with one line recommending a top pick and why.

RULES:
- Mention ONLY places from the verified results and copy their names exactly.
- Do NOT invent phone numbers, prices, ratings or addresses that are not in the data.
- If the user's preference (e.g. vegetarian, cheap) cannot be confirmed from the data, say so briefly.
- Keep it under 180 words."""


def knowledge_search_prompt(domain: str, user_goal: str, location: str, constraints_summary: str) -> str:
    """Prompt used when live map data has no results for a search."""
    return f"""The user is looking for {domain} options in {location}, but the live map lookup
returned no verified results.

USER REQUEST: "{user_goal}"

USER CONSTRAINTS:
{constraints_summary}

From your own knowledge, suggest up to 5 well-known, real {domain} options in or near {location}.
Format: a numbered markdown list, **Name** in bold followed by a dash and one line of detail.
Only include places you are confident really exist. If you do not know any, say so honestly
and suggest how the user could refine the search. Keep it under 150 words.
Do not include phone numbers or exact prices."""


def general_prompt(message: str, state_summary: str) -> str:
    """Prompt for general questions and conversation."""
    return f"""SESSION CONTEXT:
{state_summary}

USER MESSAGE: "{message}"

Answer helpfully and concisely (under 170 words) using short paragraphs and bullet lists
(no tables, no horizontal rules).
- For travel questions, give practical, specific advice for the location in the context when relevant.
- You can search hotels, restaurants, attractions and transport hubs anywhere in the world,
  build day-by-day itineraries with budgets and dates, and create study schedules -
  mention the relevant capability when it helps the user take the next step.
- Never invent exact prices, phone numbers or opening hours."""


def clarification_text(missing_fields: List[str]) -> str:
    """Deterministic clarification message (no LLM call needed)."""
    asks = []
    if "location" in missing_fields:
        asks.append(
            "**where** you'd like to go (type a city, or tap 📍 to use your current location)"
        )
    if "duration" in missing_fields:
        asks.append("**how many days** the trip is, or your travel dates")
    if not asks:
        asks = [", ".join(missing_fields)]
    return "Happy to help! I just need to know " + " and ".join(asks) + "."
