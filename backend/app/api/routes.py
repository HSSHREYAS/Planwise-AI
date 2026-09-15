"""
PlanWise AI - API Routes

Thin FastAPI layer. All business logic is in services/agent.
Based on API Specific Document Sections 6-17.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.llm.ollama_client import OllamaClient
from app.models.requests import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    MessageRequest,
    PlanResponse,
    ReplanRequest,
    ReplanResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionResponse,
)
from app.services.session_service import session_service
from app.validation.constraints import validate_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


# ── Health ──────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """GET /api/v1/health — Check backend availability."""
    llm = OllamaClient()
    return HealthResponse(
        status="ok",
        service="planwise-api",
        ollama_available=llm.is_available(),
    )


# ── Sessions ────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionCreateResponse, status_code=201)
async def create_session(request: SessionCreateRequest = None):
    """POST /api/v1/sessions — Create a new planning session."""
    session_id = session_service.create_session()
    return SessionCreateResponse(session_id=session_id, status="active")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """GET /api/v1/sessions/{session_id} — Get current session state."""
    state = session_service.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        session_id=state.session_id,
        status=state.status.value,
        state={
            "location": state.location,
            "duration_days": state.duration_days,
            "budget": state.budget,
            "preferences": state.preferences,
            "interests": state.interests,
            "chosen_options": {k: len(v) for k, v in state.chosen_options.items()},
            "has_plan": state.current_plan is not None,
        },
    )


# ── Messages ────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, request: MessageRequest):
    """
    POST /api/v1/sessions/{session_id}/messages

    Main frontend-to-agent endpoint. The most important API.
    """
    if not session_service.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(f"Message received for session {session_id}: '{request.message[:80]}'")
    response = session_service.handle_message(session_id, request.message)

    return response.model_dump()


# ── Plan ────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/plan", response_model=PlanResponse)
async def get_plan(session_id: str):
    """GET /api/v1/sessions/{session_id}/plan — Get current plan."""
    state = session_service.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    validation = None
    if state.current_plan:
        validation = validate_plan(state.current_plan, state)

    return PlanResponse(
        session_id=session_id,
        plan=state.current_plan,
        validation=validation,
    )


# ── Replan ──────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/replan")
async def replan(session_id: str, request: ReplanRequest):
    """POST /api/v1/sessions/{session_id}/replan — Replan with changes."""
    if not session_service.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(f"Replan request for session {session_id}: {request.changes}")
    response = session_service.replan(session_id, request.changes)

    return response.model_dump()
