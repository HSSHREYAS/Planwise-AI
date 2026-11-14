"""
PlanWise AI - API Routes

Thin FastAPI layer. All business logic is in services/agent.

Handlers are plain (sync) functions on purpose: the agent makes blocking
network calls, so FastAPI runs them in its thread pool and the event
loop stays responsive.
"""

import logging
import threading
from typing import List

from fastapi import APIRouter, HTTPException, Query

from app import money
from app.geo import geocoder, places
from app.geo.geocoder import Place
from app.llm.client import get_llm_client
from app.models.requests import (
    HealthResponse,
    MessageRequest,
    PlaceResponse,
    PlanResponse,
    ReplanRequest,
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
def health_check(probe: bool = Query(default=False, description="Actively test the LLM")):
    """
    GET /api/v1/health - backend availability and LLM status.

    The LLM is only called when `probe=true` (free tiers are rate limited);
    otherwise the last known status is reported.
    """
    llm = get_llm_client()
    if probe:
        available = llm.is_available()
    else:
        available = llm._availability if llm._availability is not None else bool(llm.providers)
    return HealthResponse(
        status="ok",
        service="planwise-api",
        llm_available=available,
        llm_provider=llm.provider_name,
        llm_model=llm.model,
        llm_chain=llm.describe(),
        limited_mode=llm.frugal,
    )


# ── Geo (location picker) ───────────────────────────────────────

def _place_response(place: Place) -> PlaceResponse:
    return PlaceResponse(
        name=place.name,
        label=place.label,
        display_name=place.display_name,
        lat=place.lat,
        lon=place.lon,
        country=place.country,
        country_code=place.country_code,
        currency=money.currency_for_country(place.country_code),
    )


def _prefetch(place: Place) -> None:
    """Warm the live-places cache in the background for a picked location."""
    if geocoder.is_cambridge_uk(place):
        return

    def run() -> None:
        try:
            places.fetch_places(place, ["attraction", "restaurant", "hotel"])
        except Exception as e:  # never let a warm-up crash anything
            logger.debug(f"Prefetch failed: {e}")

    threading.Thread(target=run, daemon=True).start()


@router.get("/geo/search", response_model=List[PlaceResponse])
def geo_search(q: str = Query(min_length=2, max_length=120)):
    """GET /api/v1/geo/search?q= - place autocomplete for the search bar."""
    return [_place_response(p) for p in geocoder.search(q, limit=6)]


@router.get("/geo/reverse", response_model=PlaceResponse)
def geo_reverse(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    """GET /api/v1/geo/reverse - name the user's current location."""
    place = geocoder.reverse(lat, lon)
    if place is None:
        raise HTTPException(status_code=502, detail="Could not resolve this location right now")
    _prefetch(place)
    return _place_response(place)


@router.post("/geo/prefetch", status_code=202)
def geo_prefetch(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    """POST /api/v1/geo/prefetch - warm live data for a location the user picked."""
    place = geocoder.lookup(lat, lon)
    if place is not None:
        _prefetch(place)
    return {"status": "accepted"}


# ── Sessions ────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionCreateResponse, status_code=201)
def create_session(request: SessionCreateRequest = None):
    """POST /api/v1/sessions - create a new planning session."""
    session_id = session_service.create_session()
    return SessionCreateResponse(session_id=session_id, status="active")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    """GET /api/v1/sessions/{session_id} - current session state."""
    state = session_service.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        session_id=state.session_id,
        status=state.status.value,
        state={
            "location": state.location,
            "place": state.place,
            "start_date": state.start_date,
            "end_date": state.end_date,
            "duration_days": state.duration_days,
            "budget": state.budget,
            "currency": state.currency,
            "preferences": state.preferences,
            "interests": state.interests,
            "chosen_options": {k: len(v) for k, v in state.chosen_options.items()},
            "has_plan": state.current_plan is not None,
        },
    )


# ── Messages ────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/messages")
def send_message(session_id: str, request: MessageRequest):
    """
    POST /api/v1/sessions/{session_id}/messages

    Main frontend-to-agent endpoint. Optional `context` carries the
    location and dates picked in the UI.
    """
    if not session_service.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message must not be empty")

    context = request.context.model_dump() if request.context else None
    logger.info(f"Message received for session {session_id}: '{message[:80]}'")
    response = session_service.handle_message(session_id, message, context)
    return response.model_dump()


# ── Plan ────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/plan", response_model=PlanResponse)
def get_plan(session_id: str):
    """GET /api/v1/sessions/{session_id}/plan - current plan."""
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
def replan(session_id: str, request: ReplanRequest):
    """POST /api/v1/sessions/{session_id}/replan - replan with changes."""
    if not session_service.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info(f"Replan request for session {session_id}: {request.changes}")
    response = session_service.replan(session_id, request.changes)
    return response.model_dump()
