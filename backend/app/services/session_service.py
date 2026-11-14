"""
PlanWise AI - Session Service

Manages planning sessions and coordinates between API and agent.
In-memory session storage (sufficient per project scope).
"""

import logging
import threading
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

    MAX_SESSIONS = 500

    def __init__(self):
        self._sessions: Dict[str, PlanState] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._agent = PlanningAgent()
        self._state_manager = StateManager()

    def create_session(self) -> str:
        """Create a new planning session. Returns session_id."""
        state = self._state_manager.create_state()
        if len(self._sessions) >= self.MAX_SESSIONS:
            # Drop the oldest sessions so memory stays bounded
            for old_id in list(self._sessions)[: self.MAX_SESSIONS // 10]:
                self._sessions.pop(old_id, None)
                self._locks.pop(old_id, None)
        self._sessions[state.session_id] = state
        self._locks[state.session_id] = threading.Lock()
        logger.info(f"Session created: {state.session_id}")
        return state.session_id

    def get_session(self, session_id: str) -> Optional[PlanState]:
        """Get a session's current state."""
        state = self._sessions.get(session_id)
        if state is None:
            logger.warning(f"Session not found: {session_id}")
        return state

    def handle_message(
        self,
        session_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
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

        # One message at a time per session (the state is mutated in place)
        with self._locks.setdefault(session_id, threading.Lock()):
            return self._agent.handle_message(message, state, context)

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

        if state.current_plan is None:
            return AgentResponse(
                session_id=session_id,
                status=ResponseStatus.ERROR,
                message="There is no plan to change yet. Ask me to plan a trip first.",
            )

        with self._locks.setdefault(session_id, threading.Lock()):
            return self._agent.replan_with_changes(state, changes)

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)


# Module-level singleton
session_service = SessionService()
