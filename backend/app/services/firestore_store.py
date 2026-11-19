"""Firestore persistence for private PlanWise sessions and profile data."""

from datetime import datetime, timezone
import base64
import logging
import threading
from typing import Any, Dict, List, Optional
import zlib

from app.auth import get_firebase_admin_app
from app.models.schemas import PlanState

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()


def _db():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from firebase_admin import firestore

                _client = firestore.client(app=get_firebase_admin_app())
    return _client


def _user_ref(uid: str):
    return _db().collection("users").document(uid)


def save_session(uid: str, state: PlanState) -> None:
    """Save a complete session snapshot under its verified Firebase owner."""
    user_messages = [m.content.strip() for m in state.conversation_history if m.role == "user" and m.content.strip()]
    title = user_messages[0] if user_messages else "New trip conversation"
    last_message = state.conversation_history[-1].content if state.conversation_history else ""
    session_doc = {
        "session_id": state.session_id,
        "state_compressed": base64.b64encode(zlib.compress(state.model_dump_json().encode("utf-8"), level=6)).decode("ascii"),
        "title": title[:180],
        "last_message": last_message[:240],
        "location": state.location or "",
        "has_plan": state.current_plan is not None,
        "message_count": len(state.conversation_history),
        "created_at": state.created_at.isoformat(),
        "updated_at": datetime.now(timezone.utc),
    }
    _user_ref(uid).collection("sessions").document(state.session_id).set(
        session_doc, retry=None, timeout=10,
    )


def load_session(uid: str, session_id: str) -> Optional[PlanState]:
    snapshot = _user_ref(uid).collection("sessions").document(session_id).get(
        retry=None, timeout=10,
    )
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    compressed_state = data.get("state_compressed")
    raw_state = data.get("state_json")
    if isinstance(compressed_state, str):
        try:
            raw_state = zlib.decompress(base64.b64decode(compressed_state)).decode("utf-8")
        except (ValueError, zlib.error, UnicodeDecodeError):
            logger.exception("Stored session %s has invalid compressed state", session_id)
            return None
    if not isinstance(raw_state, str):
        logger.error("Stored session %s has no valid state snapshot", session_id)
        return None
    state = PlanState.model_validate_json(raw_state)
    if state.session_id != session_id:
        logger.error("Stored session ID did not match its Firestore document")
        return None
    return state


def list_sessions(uid: str) -> List[Dict[str, Any]]:
    from firebase_admin import firestore

    snapshots = (
        _user_ref(uid).collection("sessions")
        .order_by("updated_at", direction=firestore.Query.DESCENDING)
        .stream(retry=None, timeout=10)
    )
    results = []
    for snapshot in snapshots:
        item = snapshot.to_dict() or {}
        if not item.get("message_count"):
            continue
        updated = item.get("updated_at")
        results.append({
            "session_id": snapshot.id,
            "title": item.get("title") or "Trip conversation",
            "last_message": item.get("last_message") or "",
            "location": item.get("location") or "",
            "has_plan": bool(item.get("has_plan")),
            "message_count": int(item.get("message_count") or 0),
            "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else None,
        })
    return results


def get_profile(uid: str) -> Dict[str, Any]:
    snapshot = _user_ref(uid).collection("private").document("profile").get(
        retry=None, timeout=10,
    )
    return snapshot.to_dict() if snapshot.exists else {}


def save_profile(uid: str, values: Dict[str, Any]) -> Dict[str, Any]:
    ref = _user_ref(uid).collection("private").document("profile")
    profile = {
        **values,
        "updated_at": datetime.now(timezone.utc),
    }
    # A merge preserves any existing creation metadata without an extra read.
    ref.set(profile, merge=True, retry=None, timeout=15)
    return profile
