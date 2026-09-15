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
            elif key == "duration_days" and isinstance(value, int):
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
            else:
                logger.warning(f"Unknown change key: {key}={value}")

        # Increment replan counter
        state.replan_count += 1
        return state

    @staticmethod
    def get_conversation_summary(state: PlanState) -> str:
        """Build a text summary of the current state for LLM context."""
        parts = []

        if state.location:
            parts.append(f"Location: {state.location}")
        if state.duration_days is not None:
            parts.append(f"Duration: {state.duration_days} day(s)")
        if state.budget is not None:
            parts.append(f"Budget: ₹{state.budget}")
        if state.preferences:
            parts.append(f"Preferences: {', '.join(state.preferences)}")
        if state.interests:
            parts.append(f"Interests: {', '.join(state.interests)}")
        if state.goal:
            parts.append(f"Goal: {state.goal}")
        if state.current_plan:
            parts.append(f"Has existing plan: Yes (replan #{state.replan_count})")

        # Recent conversation (last 4 messages)
        if state.conversation_history:
            recent = state.conversation_history[-4:]
            conv_lines = []
            for msg in recent:
                prefix = "User" if msg.role == "user" else "Assistant"
                content_preview = msg.content[:150]
                conv_lines.append(f"  {prefix}: {content_preview}")
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
        if state.location:
            parts.append(f"Location: {state.location}")
        if state.duration_days is not None:
            parts.append(f"Duration: {state.duration_days} day(s)")
        if state.budget is not None:
            parts.append(f"Budget: ₹{state.budget}")
        if state.preferences:
            parts.append(f"Preferences: {', '.join(state.preferences)}")
        if state.interests:
            parts.append(f"Interests: {', '.join(state.interests)}")
        return "\n".join(parts) if parts else "No constraints specified."

    @staticmethod
    def get_retrieved_options_summary(state: PlanState) -> str:
        """Build text summary of all retrieved tool results for LLM context."""
        if not state.chosen_options:
            return "No options retrieved yet."

        parts = []
        for domain, records in state.chosen_options.items():
            parts.append(f"\n{domain.upper()} OPTIONS:")
            for i, rec in enumerate(records[:10], 1):
                name = rec.get("name", "Unknown")
                details_parts = []
                for key in ["area", "pricerange", "food", "type", "stars",
                            "entrance_fee", "price", "address"]:
                    if key in rec and rec[key]:
                        details_parts.append(f"{key}: {rec[key]}")
                details_str = ", ".join(details_parts)
                parts.append(f"  {i}. {name} ({details_str})")

        return "\n".join(parts)
