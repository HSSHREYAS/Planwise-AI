"""
PlanWise AI - Session Service

Manages planning sessions and coordinates between API and agent.
In-memory session storage (sufficient per project scope).
"""

import logging
from typing import Any, Dict, Optional

from app.agent.planner import PlanningAgent
from app.models.schemas import (
    AgentResponse,
    Plan,
    PlanState,
    ResponseStatus,
)
from app.state.manager import StateManager

logger = logging.getLogger(__name__)


class SessionService:
    """
    Manages planning sessions.

    Session lifecycle:
        create → handle_message(s) → get_plan → replan → ...
    """

    def __init__(self):
        self._sessions: Dict[str, PlanState] = {}
        self._agent = PlanningAgent()
        self._state_manager = StateManager()

    def create_session(self) -> str:
        """Create a new planning session. Returns session_id."""
        state = self._state_manager.create_state()
        self._sessions[state.session_id] = state
        logger.info(f"Session created: {state.session_id}")
        return state.session_id

    def get_session(self, session_id: str) -> Optional[PlanState]:
        """Get a session's current state."""
        state = self._sessions.get(session_id)
        if state is None:
            logger.warning(f"Session not found: {session_id}")
        return state

    def handle_message(
        self, session_id: str, message: str
    ) -> AgentResponse:
        """
        Process a user message through the planning agent.
        This is the most important service method.
        """
        state = self._sessions.get(session_id)
        if state is None:
            return AgentResponse(
                session_id=session_id,
                status=ResponseStatus.ERROR,
                message="Session not found. Please start a new session.",
            )

        # Run agent
        response = self._agent.handle_message(message, state)

        # State is mutated in-place by the agent, but update reference
        self._sessions[session_id] = state

        return response

    def get_plan(self, session_id: str) -> Optional[Plan]:
        """Get the current plan for a session."""
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.current_plan

    def replan(
        self, session_id: str, changes: Dict[str, Any]
    ) -> AgentResponse:
        """
        Handle explicit replanning with changed constraints.

        Args:
            session_id: Session to replan
            changes: Dict of changed constraints (e.g. {"budget": 1500})
        """
        state = self._sessions.get(session_id)
        if state is None:
            return AgentResponse(
                session_id=session_id,
                status=ResponseStatus.ERROR,
                message="Session not found. Please start a new session.",
            )

        # Apply changes to state
        state = self._state_manager.apply_changes(state, changes)

        # Build a natural language message describing the changes
        change_parts = []
        for key, value in changes.items():
            change_parts.append(f"Change {key} to {value}")
        change_message = ". ".join(change_parts)

        # Process through agent
        response = self._agent.handle_message(change_message, state)
        self._sessions[session_id] = state

        return response

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)


# Module-level singleton
session_service = SessionService()
