"""
PlanWise AI - Session Service

Manages planning sessions and coordinates between API and agent.
In-memory working state with user-owned snapshots persisted to Firestore by the API.

Every request works on a private copy of the session state and only
commits it back when it finishes. That makes a request cancellable: if the
user presses Stop, the copy is thrown away and the session is exactly as it
was before the cancelled message - and the next message can start right
away instead of waiting for the cancelled one to finish.
"""

import logging
import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

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
    MAX_CANCELLED_IDS = 2000

    def __init__(self):
        self._sessions: Dict[str, PlanState] = {}
        self._versions: Dict[str, int] = {}
        self._owners: Dict[str, str] = {}
        self._lock = threading.Lock()   # guards the dictionaries, never held during agent work
        self._cancelled: "OrderedDict[str, None]" = OrderedDict()
        self._agent = PlanningAgent()
        self._state_manager = StateManager()

    def create_session(self, owner_uid: Optional[str] = None) -> str:
        """Create a new planning session. Returns session_id."""
        state = self._state_manager.create_state()
        with self._lock:
            if len(self._sessions) >= self.MAX_SESSIONS:
                # Drop the oldest sessions so memory stays bounded
                for old_id in list(self._sessions)[: self.MAX_SESSIONS // 10]:
                    self._sessions.pop(old_id, None)
                    self._versions.pop(old_id, None)
                    self._owners.pop(old_id, None)
            self._sessions[state.session_id] = state
            self._versions[state.session_id] = 0
            if owner_uid:
                self._owners[state.session_id] = owner_uid
        logger.info(f"Session created: {state.session_id}")
        return state.session_id

    def get_session(self, session_id: str) -> Optional[PlanState]:
        """Get a session's current state."""
        state = self._sessions.get(session_id)
        if state is None:
            logger.warning(f"Session not found: {session_id}")
        return state

    def restore_session(self, state: PlanState, owner_uid: str) -> bool:
        """Load a persisted, owner-scoped state into this process's memory."""
        with self._lock:
            known_owner = self._owners.get(state.session_id)
            if known_owner and known_owner != owner_uid:
                return False
            if state.session_id not in self._sessions:
                self._sessions[state.session_id] = state
                self._versions[state.session_id] = 0
            self._owners[state.session_id] = owner_uid
        return True

    # ── Running requests ────────────────────────────────────────

    def _run(
        self,
        session_id: str,
        request_id: Optional[str],
        work: Callable[[PlanState], AgentResponse],
    ) -> AgentResponse:
        """Run `work` on a copy of the session state and commit it unless cancelled."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return AgentResponse(
                    session_id=session_id,
                    status=ResponseStatus.ERROR,
                    message="Session not found. Please start a new session.",
                )
            if request_id and request_id in self._cancelled:
                return self._cancelled_response(session_id)
            snapshot = state.model_copy(deep=True)
            version = self._versions.get(session_id, 0)

        response = work(snapshot)

        with self._lock:
            if request_id and request_id in self._cancelled:
                logger.info(f"Request {request_id} was cancelled - discarding its result")
                return self._cancelled_response(session_id)
            if session_id not in self._sessions:
                return response
            if self._versions.get(session_id, 0) != version:
                # Another request finished first; keep its state rather than overwrite it
                logger.warning(f"Session {session_id} changed during the request - result not saved")
                return response
            self._sessions[session_id] = snapshot
            self._versions[session_id] = version + 1
        return response

    @staticmethod
    def _cancelled_response(session_id: str) -> AgentResponse:
        return AgentResponse(
            session_id=session_id,
            status=ResponseStatus.CANCELLED,
            message="This request was cancelled.",
        )

    def cancel(self, session_id: str, request_id: str) -> None:
        """Mark a request as cancelled; its result will be discarded."""
        with self._lock:
            self._cancelled[request_id] = None
            while len(self._cancelled) > self.MAX_CANCELLED_IDS:
                self._cancelled.popitem(last=False)
        logger.info(f"Cancel requested for {request_id} (session {session_id})")

    def handle_message(
        self,
        session_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> AgentResponse:
        """
        Process a user message through the planning agent.
        This is the most important service method.
        """
        return self._run(
            session_id, request_id,
            lambda state: self._agent.handle_message(message, state, context),
        )

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

        return self._run(
            session_id, None,
            lambda snapshot: self._agent.replan_with_changes(snapshot, changes),
        )

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    def session_belongs_to(self, session_id: str, owner_uid: str) -> bool:
        """Check whether a session belongs to a Firebase user."""
        with self._lock:
            return self._owners.get(session_id) == owner_uid

    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)


# Module-level singleton
session_service = SessionService()
