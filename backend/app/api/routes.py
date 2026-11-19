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

from fastapi import APIRouter, Depends, HTTPException, Query

from app import money
from app.auth import get_current_user, public_firebase_config
from app.geo import geocoder, places
from app.geo.geocoder import Place
from app.llm.client import get_llm_client
from app.models.requests import (
    HealthResponse,
    MessageRequest,
    PlaceResponse,
    PlanResponse,
    ProfileUpdate,
    ReplanRequest,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionResponse,
)
from app.services import firestore_store
from app.services.session_service import session_service
from app.validation.constraints import validate_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _storage_unavailable(exc: Exception) -> HTTPException:
    logger.exception("Firebase user data could not be read or saved (%s)", type(exc).__name__)
    return HTTPException(
        status_code=503,
        detail="PlanWise account storage is unavailable. Enable Cloud Firestore for this Firebase project and try again.",
    )


@router.get("/auth/config")
def auth_config():
    """Return browser-safe Firebase settings and whether sign-in is configured."""
    return public_firebase_config()


@router.get("/profile")
def get_profile(user: dict = Depends(get_current_user)):
    """Get the signed-in user's private profile and trip preferences."""
    try:
        stored = firestore_store.get_profile(user["uid"])
    except Exception as exc:
        raise _storage_unavailable(exc) from exc
    return {
        "display_name": stored.get("display_name") or user.get("name") or "",
        "email": user.get("email") or "",
        "hometown": stored.get("hometown", ""),
        "bio": stored.get("bio", ""),
        "languages": stored.get("languages", []),
        "interests": stored.get("interests", []),
        "default_travelers": stored.get("default_travelers", 1),
        "preferred_currency": stored.get("preferred_currency", "USD"),
        "preferred_trip_style": stored.get("preferred_trip_style", ""),
    }


@router.put("/profile")
def update_profile(request: ProfileUpdate, user: dict = Depends(get_current_user)):
    """Save private profile details and default travel preferences."""
    values = request.model_dump()
    values["display_name"] = values["display_name"].strip()
    values["hometown"] = values["hometown"].strip()
    values["bio"] = values["bio"].strip()
    values["preferred_trip_style"] = values["preferred_trip_style"].strip()
    values["languages"] = [value for value in (item.strip() for item in values["languages"]) if value]
    values["interests"] = [value for value in (item.strip() for item in values["interests"]) if value]
    values["preferred_currency"] = values["preferred_currency"].upper()
    try:
        stored = firestore_store.save_profile(user["uid"], values)
    except Exception as exc:
        raise _storage_unavailable(exc) from exc
    return {**values, "email": user.get("email") or "", "updated_at": stored["updated_at"]}


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
        available = llm.is_available(max_age=0)
    else:
        available = llm._availability if llm._availability is not None else bool(llm.providers)
    return HealthResponse(
        status="ok",
        service="planwise-api",
        llm_available=available,
        llm_provider=llm.provider_name,
        llm_model=llm.model,
        llm_chain=llm.describe(),
        llm_errors=dict(llm.last_errors),
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

def _require_owned_session(session_id: str, user: dict) -> None:
    uid = user["uid"]
    if session_service.session_belongs_to(session_id, uid):
        return
    try:
        state = firestore_store.load_session(uid, session_id)
    except Exception as exc:
        raise _storage_unavailable(exc) from exc
    if state is None or not session_service.restore_session(state, uid):
        # Do not reveal whether another account's session ID exists.
        raise HTTPException(status_code=404, detail="Session not found")


def _persist_session(session_id: str, uid: str) -> None:
    state = session_service.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        firestore_store.save_session(uid, state)
    except Exception as exc:
        raise _storage_unavailable(exc) from exc


@router.post("/sessions", response_model=SessionCreateResponse, status_code=201)
def create_session(
    request: SessionCreateRequest = None,
    user: dict = Depends(get_current_user),
):
    """POST /api/v1/sessions - create a new planning session."""
    session_id = session_service.create_session(owner_uid=user["uid"])
    # Keep session startup independent of Firestore. The first durable snapshot
    # is written after a conversation has actually been created.
    return SessionCreateResponse(session_id=session_id, status="active")


def _persist_response_session(session_id: str, uid: str, response) -> None:
    """Persist history without discarding a completed planner response on failure."""
    try:
        _persist_session(session_id, uid)
    except HTTPException as exc:
        logger.warning("Planner response is ready but session history was not saved: %s", exc.detail)
        response.context["persistence_warning"] = (
            "Your answer is ready, but this conversation could not be saved to history."
        )


@router.get("/sessions")
def list_sessions(user: dict = Depends(get_current_user)):
    """List the current user's saved conversations and plans."""
    try:
        return {"sessions": firestore_store.list_sessions(user["uid"])}
    except Exception as exc:
        raise _storage_unavailable(exc) from exc


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, user: dict = Depends(get_current_user)):
    """GET /api/v1/sessions/{session_id} - current session state."""
    _require_owned_session(session_id, user)
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
            "conversation": [item.model_dump(mode="json") for item in state.conversation_history],
            "plan": state.current_plan.model_dump(mode="json") if state.current_plan else None,
            "validation": validate_plan(state.current_plan, state).model_dump(mode="json") if state.current_plan else None,
            "context": {
                "location": state.location,
                "lat": (state.place or {}).get("lat"),
                "lon": (state.place or {}).get("lon"),
                "start_date": state.start_date,
                "end_date": state.end_date,
                "duration_days": state.duration_days,
                "budget": state.budget,
                "travelers": state.travelers,
                "currency": state.currency,
            },
        },
    )


# ── Messages ────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: str,
    request: MessageRequest,
    user: dict = Depends(get_current_user),
):
    """
    POST /api/v1/sessions/{session_id}/messages

    Main frontend-to-agent endpoint. Optional `context` carries the
    location and dates picked in the UI.
    """
    _require_owned_session(session_id, user)

    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message must not be empty")

    context = request.context.model_dump() if request.context else None
    logger.info(f"Message received for session {session_id}: '{message[:80]}'")
    response = session_service.handle_message(session_id, message, context, request.request_id)
    if response.status.value != "cancelled":
        _persist_response_session(session_id, user["uid"], response)
    return response.model_dump()


@router.post("/sessions/{session_id}/messages/{request_id}/cancel", status_code=202)
def cancel_message(
    session_id: str,
    request_id: str,
    user: dict = Depends(get_current_user),
):
    """
    POST /api/v1/sessions/{session_id}/messages/{request_id}/cancel

    Stop button: the message's result is discarded and the session stays as
    it was before that message.
    """
    _require_owned_session(session_id, user)
    if len(request_id) > 64:
        raise HTTPException(status_code=422, detail="Invalid request id")
    session_service.cancel(session_id, request_id)
    return {"status": "cancelled", "request_id": request_id}


# ── Plan ────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/plan", response_model=PlanResponse)
def get_plan(session_id: str, user: dict = Depends(get_current_user)):
    """GET /api/v1/sessions/{session_id}/plan - current plan."""
    _require_owned_session(session_id, user)
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
def replan(
    session_id: str,
    request: ReplanRequest,
    user: dict = Depends(get_current_user),
):
    """POST /api/v1/sessions/{session_id}/replan - replan with changes."""
    _require_owned_session(session_id, user)

    logger.info(f"Replan request for session {session_id}: {request.changes}")
    response = session_service.replan(session_id, request.changes)
    if response.status.value != "cancelled":
        _persist_response_session(session_id, user["uid"], response)
    return response.model_dump()
