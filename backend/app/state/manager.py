"""
PlanWise AI - State Manager

Manages the PlanState lifecycle: creation, updates, and change application.
State is the source of truth for the current planning session.
"""

import logging
from typing import Any, Dict, List, Optional

from app.models.schemas import (
    AgentStatus,
    ConversationMessage,
    IntentResult,
    Plan,
    PlanState,
    Task,
    ToolResult,
    normalize_iso_date,
)

logger = logging.getLogger(__name__)


class StateManager:
    """Manages PlanState updates with proper semantics."""

    @staticmethod
    def create_state(session_id: Optional[str] = None) -> PlanState:
        """Create a fresh planning state."""
        state = PlanState()
        if session_id:
            state.session_id = session_id
        logger.info(f"Created new state: session_id={state.session_id}")
        return state

    @staticmethod
    def update_from_intent(state: PlanState, intent: IntentResult) -> PlanState:
        """
        Update state from an intent result.
        Merges new information without overwriting existing values
        unless the new value is explicitly provided.
        """
        state.intent = intent.intent

        # Update location if provided
        if intent.location:
            if state.location and state.location != intent.location:
                logger.info(
                    f"Location changed: {state.location} → {intent.location}"
                )
            state.location = intent.location

        # Update duration if provided
        if intent.duration_days is not None:
            if (
                state.duration_days is not None
                and state.duration_days != intent.duration_days
            ):
                logger.info(
                    f"Duration changed: {state.duration_days} → {intent.duration_days}"
                )
            state.duration_days = intent.duration_days

        # Update budget if provided
        if intent.budget is not None:
            if state.budget is not None and state.budget != intent.budget:
                logger.info(f"Budget changed: {state.budget} → {intent.budget}")
            state.budget = intent.budget

        # Merge preferences (additive, no duplicates)
        if intent.preferences:
            for pref in intent.preferences:
                pref_lower = pref.lower().strip()
                if pref_lower and pref_lower not in [
                    p.lower() for p in state.preferences
                ]:
                    state.preferences.append(pref_lower)
                    logger.info(f"Preference added: {pref_lower}")

        # Merge interests (additive, no duplicates)
        if intent.interests:
            for interest in intent.interests:
                interest_lower = interest.lower().strip()
                if interest_lower and interest_lower not in [
                    i.lower() for i in state.interests
                ]:
                    state.interests.append(interest_lower)
                    logger.info(f"Interest added: {interest_lower}")

        return state

    @staticmethod
    def update_from_tool_result(
        state: PlanState, result: ToolResult
    ) -> PlanState:
        """Store tool results in state."""
        state.tool_results.append(result)

        # Also update chosen_options by domain
        if result.success and result.results:
            domain = result.tool_name.replace("_search", "").replace("search_", "")
            if domain not in state.chosen_options:
                state.chosen_options[domain] = []
            state.chosen_options[domain] = result.results
            logger.info(
                f"Stored {len(result.results)} {domain} results in state"
            )

        return state

    @staticmethod
    def update_plan(state: PlanState, plan: Plan) -> PlanState:
        """Update the current plan in state."""
        state.current_plan = plan
        logger.info("Plan updated in state")
        return state

    @staticmethod
    def set_status(state: PlanState, status: AgentStatus) -> PlanState:
        """Update the agent status."""
        logger.debug(f"Status: {state.status} → {status}")
        state.status = status
        return state

    @staticmethod
    def add_message(
        state: PlanState, role: str, content: str
    ) -> PlanState:
        """Add a message to conversation history."""
        state.conversation_history.append(
            ConversationMessage(role=role, content=content)
        )
        return state

    @staticmethod
    def set_goal(state: PlanState, goal: str) -> PlanState:
        """Set the current planning goal."""
        state.goal = goal
        return state

    @staticmethod
    def set_subtasks(state: PlanState, tasks: List[Task]) -> PlanState:
        """Set the decomposed subtasks."""
        state.subtasks = tasks
        return state

    @staticmethod
    def set_violations(state: PlanState, violations: List[str]) -> PlanState:
        """Set constraint violations."""
        state.violations = violations
        return state

    @staticmethod
    def apply_changes(state: PlanState, changes: Dict[str, Any]) -> PlanState:
        """
        Apply explicit changes for replanning.
        Used when user says e.g. "reduce budget to 1500".
        """
        for key, value in changes.items():
            if key == "budget" and isinstance(value, (int, float)):
                logger.info(f"Replan: budget {state.budget} → {value}")
                state.budget = float(value)
            elif key == "budget" and isinstance(value, str) and value.replace(".", "", 1).isdigit():
                state.budget = float(value)
            elif key == "duration_days" and isinstance(value, str) and value.isdigit():
                state.duration_days = int(value)
            elif key == "duration_days" and isinstance(value, (int, float)) and not isinstance(value, bool):
                value = int(value)
                logger.info(
                    f"Replan: duration {state.duration_days} → {value}"
                )
                state.duration_days = value
            elif key == "preferences" and isinstance(value, list):
                logger.info(f"Replan: preferences updated to {value}")
                state.preferences = [p.lower().strip() for p in value]
            elif key == "interests" and isinstance(value, list):
                logger.info(f"Replan: interests updated to {value}")
                state.interests = [i.lower().strip() for i in value]
            elif key == "location" and isinstance(value, str):
                logger.info(f"Replan: location {state.location} → {value}")
                state.location = value
                state.place = None
            elif key in ("start_date", "end_date") and isinstance(value, str):
                setattr(state, key, normalize_iso_date(value) or getattr(state, key))
            elif key == "currency" and isinstance(value, str) and len(value.strip()) == 3:
                state.currency = value.strip().upper()
            elif key in ("travelers", "travellers", "people") and str(value).strip().isdigit():
                logger.info(f"Replan: travellers {state.travelers} → {value}")
                state.travelers = max(1, min(int(value), 50))
            else:
                logger.warning(f"Unknown change key: {key}={value}")

        # Increment replan counter
        state.replan_count += 1
        return state

    @staticmethod
    def _context_lines(state: PlanState) -> List[str]:
        parts = []
        if state.location:
            parts.append(f"Location: {state.location}")
        if state.start_date:
            dates = f"Dates: {state.start_date}"
            if state.end_date:
                dates += f" to {state.end_date}"
            parts.append(dates)
        if state.duration_days is not None:
            parts.append(f"Duration: {state.duration_days} day(s)")
        if (state.travelers or 1) > 1:
            parts.append(f"Travellers: {state.travelers} people")
        if state.budget is not None:
            scope = " (whole group)" if (state.travelers or 1) > 1 else ""
            parts.append(f"Budget: {state.budget:g} {state.currency or ''}".rstrip() + scope)
        elif state.currency:
            parts.append(f"Currency for costs: {state.currency}")
        if state.preferences:
            parts.append(f"Preferences: {', '.join(state.preferences)}")
        if state.interests:
            parts.append(f"Interests: {', '.join(state.interests)}")
        return parts

    @staticmethod
    def get_conversation_summary(state: PlanState) -> str:
        """Build a text summary of the current state for LLM context."""
        parts = StateManager._context_lines(state)
        if state.current_plan:
            parts.append(f"Has existing plan: Yes (replan #{state.replan_count})")

        # Recent conversation (previous 4 messages, excluding the newest one)
        history = state.conversation_history[:-1][-4:]
        if history:
            conv_lines = []
            for msg in history:
                prefix = "User" if msg.role == "user" else "Assistant"
                conv_lines.append(f"  {prefix}: {msg.content[:150]}")
            parts.append("Recent conversation:\n" + "\n".join(conv_lines))

        return "\n".join(parts) if parts else "No state information available."

    @staticmethod
    def get_state_summary(state: PlanState) -> str:
        """Short state summary for constraint and plan contexts."""
        parts = []
        if state.goal:
            parts.append(f"Goal: {state.goal}")
        if state.intent:
            parts.append(f"Intent: {state.intent}")
        parts.extend(StateManager._context_lines(state))
        return "\n".join(parts) if parts else "No constraints specified."

    @staticmethod
    def get_retrieved_options_summary(state: PlanState, per_domain: int = 10) -> str:
        """Build text summary of all retrieved tool results for LLM context."""
        if not any(state.chosen_options.values()):
            return "No options retrieved (none available for this location)."

        detail_keys = [
            "type", "food", "area", "pricerange", "stars", "vegetarian",
            "entrance_fee", "price", "departure", "destination", "leaveAt",
            "arriveBy", "duration", "code", "opening_hours", "address",
        ]
        parts = []
        for domain, records in state.chosen_options.items():
            if not records:
                continue
            parts.append(f"\n{domain.upper()} OPTIONS:")
            for i, rec in enumerate(records[:per_domain], 1):
                name = rec.get("name", "Unknown")
                details = [
                    f"{key}: {rec[key]}" for key in detail_keys
                    if rec.get(key) not in (None, "", "?")
                ]
                if rec.get("distance_km") is not None:
                    details.append(f"{rec['distance_km']} km from centre")
                parts.append(f"  {i}. {name} ({', '.join(details)})")

        return "\n".join(parts)
