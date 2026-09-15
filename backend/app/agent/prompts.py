"""
PlanWise AI - Prompt Templates

All LLM prompt templates, separated from Python logic.
Based on Architecture doc Section 11.

Each prompt clearly specifies:
- Role the model is performing
- State/data it receives
- Expected output schema
- Hallucination guard: "Do not invent information not provided"
"""


def intent_prompt(message: str, conversation_summary: str = "") -> str:
    """Prompt for understanding user intent and extracting parameters."""
    context_section = ""
    if conversation_summary:
        context_section = f"""
CONVERSATION CONTEXT (previous state):
{conversation_summary}
"""

    return f"""You are PlanWise AI's intent understanding module.

Analyze the user's message and extract their planning intent.
{context_section}
USER MESSAGE: "{message}"

Respond with ONLY a JSON object (no markdown, no explanation) with these fields:
{{
    "intent": "<one of: trip_planning, hotel_search, restaurant_search, attraction_search, transport_search, study_planning, schedule_generation, replanning, general_query>",
    "location": "<location string or null>",
    "duration_days": <number or null>,
    "budget": <number or null>,
    "preferences": ["<list of preferences like vegetarian, budget-friendly, etc.>"],
    "interests": ["<list of interests like culture, food, history, etc.>"],
    "is_modification": <true if user is changing an existing plan, false otherwise>,
    "raw_changes": {{"<field>": "<new_value>"}} or null
}}

RULES:
- If the user mentions changing budget, duration, preferences on an existing plan, set is_modification=true and raw_changes accordingly.
- Extract ALL mentioned constraints and preferences.
- If something is not mentioned, use null or empty list.
- Do NOT invent information the user did not provide.
- Respond with ONLY the JSON object."""


def decomposition_prompt(state_summary: str) -> str:
    """Prompt for decomposing a goal into subtasks."""
    return f"""You are PlanWise AI's task decomposition module.

Given the current planning state, decompose the goal into executable subtasks.

CURRENT STATE:
{state_summary}

Available tools:
- hotel_search: Search for hotels (params: location, budget, preferences)
- restaurant_search: Search for restaurants (params: location, budget, preferences)
- attraction_search: Search for attractions (params: location, interests)
- transport_search: Search for transport options (params: location, source, destination)

Respond with ONLY a JSON object:
{{
    "tasks": [
        {{
            "task_type": "<one of: search_hotels, search_restaurants, search_attractions, search_transport, generate_schedule>",
            "parameters": {{"<param>": "<value>"}}
        }}
    ]
}}

RULES:
- Only include tasks relevant to the user's request.
- For trip planning, typically include: attractions, restaurants, and optionally hotels/transport.
- For study planning, just include generate_schedule (no search tools needed).
- Use information from the current state for parameters.
- Do NOT include tasks for domains the user didn't ask about.
- Respond with ONLY the JSON object."""


def schedule_prompt(
    state_summary: str,
    retrieved_options: str,
    constraints_summary: str,
) -> str:
    """Prompt for generating a candidate schedule/plan."""
    return f"""You are PlanWise AI's schedule generation module.

Generate a structured day-by-day plan using ONLY the retrieved options below.

CURRENT STATE:
{state_summary}

CONSTRAINTS:
{constraints_summary}

AVAILABLE OPTIONS (from MultiWOZ 2.2 local data — Cambridge, UK — use ONLY these):
{retrieved_options}

Respond with ONLY a JSON object:
{{
    "location": "<location or null>",
    "duration_days": <number>,
    "days": [
        {{
            "day": 1,
            "slots": [
                {{
                    "time_of_day": "morning",
                    "activities": [
                        {{
                            "name": "<exact name from retrieved options>",
                            "type": "<attraction/restaurant/transport/hotel>",
                            "estimated_cost": <number or null>,
                            "duration_minutes": <number or null>,
                            "details": {{}}
                        }}
                    ]
                }},
                {{
                    "time_of_day": "afternoon",
                    "activities": [...]
                }},
                {{
                    "time_of_day": "evening",
                    "activities": [...]
                }}
            ]
        }}
    ],
    "estimated_total_cost": <total estimated cost or null>,
    "assumptions": ["<any assumptions made>"],
    "plan_type": "trip"
}}

RULES:
- Use ONLY names and details from the AVAILABLE OPTIONS above.
- Do NOT invent places, restaurants, or attractions not listed.
- Distribute activities reasonably across days and time slots.
- Keep total estimated cost within the budget if one is specified.
- If there aren't enough options, use fewer activities rather than inventing.
- Each day should have morning, afternoon, and evening slots.
- Respond with ONLY the JSON object."""


def study_schedule_prompt(state_summary: str, constraints_summary: str) -> str:
    """Prompt for generating a study/personal schedule."""
    return f"""You are PlanWise AI's study schedule generation module.

Generate a structured study schedule based on the user's requirements.

CURRENT STATE:
{state_summary}

CONSTRAINTS:
{constraints_summary}

Respond with ONLY a JSON object:
{{
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
                            "name": "<study topic/subject>",
                            "type": "study",
                            "estimated_cost": null,
                            "duration_minutes": <number>,
                            "details": {{"description": "<what to study>"}}
                        }}
                    ]
                }},
                {{
                    "time_of_day": "afternoon",
                    "activities": [...]
                }},
                {{
                    "time_of_day": "evening",
                    "activities": [...]
                }}
            ]
        }}
    ],
    "estimated_total_cost": null,
    "assumptions": ["<any assumptions made>"],
    "plan_type": "study"
}}

RULES:
- Create a realistic and balanced study schedule.
- Include breaks and variety if multiple subjects are mentioned.
- Respect any time constraints the user mentioned.
- Respond with ONLY the JSON object."""


def replanning_prompt(
    state_summary: str,
    current_plan_summary: str,
    violations: str,
    retrieved_options: str,
) -> str:
    """Prompt for revising an existing plan after constraint changes."""
    return f"""You are PlanWise AI's replanning module.

The current plan has constraint violations. Revise it to fix the violations
while preserving as much of the existing plan as possible.

CURRENT STATE:
{state_summary}

CURRENT PLAN:
{current_plan_summary}

VIOLATIONS:
{violations}

AVAILABLE OPTIONS (use ONLY these):
{retrieved_options}

Generate a REVISED plan as a JSON object with the same structure as the original.
Fix the violations while keeping unchanged parts of the plan intact.

RULES:
- Fix ALL listed violations.
- Prefer cheaper alternatives if budget is the issue.
- Remove activities if needed to fit within budget.
- Use ONLY names from the available options.
- Do NOT invent new places or options.
- Respond with ONLY the JSON object."""


def response_prompt(plan_summary: str, state_summary: str) -> str:
    """Prompt for generating the final user-facing natural language response."""
    return f"""You are PlanWise AI's response generator.

Convert the verified plan into a clear, friendly natural language response for the user.

PLAN:
{plan_summary}

STATE:
{state_summary}

Write a clear, well-organized response that includes:
1. A brief acknowledgment of what was planned
2. The day-by-day schedule with times and activities
3. Budget information if applicable
4. Any relevant notes or assumptions

Keep it concise and readable. Use simple formatting.
Do NOT add information that isn't in the plan above.
Do NOT invent additional places or costs."""


def clarification_prompt(missing_fields: list, state_summary: str) -> str:
    """Prompt for generating a clarification request when info is missing."""
    fields_str = ", ".join(missing_fields)
    return f"""You are PlanWise AI.

The user wants to create a plan, but some important information is missing.

CURRENT STATE:
{state_summary}

MISSING INFORMATION: {fields_str}

Write a brief, friendly message asking the user to provide the missing information.
Be specific about what you need. Keep it to 1-2 sentences."""


def search_results_prompt(domain: str, options_summary: str, user_goal: str) -> str:
    """Prompt for formatting single-domain search results."""
    return f"""You are PlanWise AI's response generator.

The user searched for {domain} options. Present the results in a clear, helpful way.

USER REQUEST: "{user_goal}"

SEARCH RESULTS:
{options_summary}

Write a clear, well-organized response that:
1. Briefly acknowledges the search
2. Lists each {domain} option with its key details (name, area, price, type, etc.)
3. Highlights any standout options
4. Notes that all data is from Cambridge, UK (MultiWOZ 2.2 dataset)

Use simple formatting with bullet points or numbered lists.
Do NOT invent information not present in the search results above.
Keep it concise and readable."""

