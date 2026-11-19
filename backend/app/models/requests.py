"""
PlanWise AI - API Request/Response Models

Pydantic models for API layer validation.
Based on API Specific Document Sections 7-17, 22.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, constr

from app.models.schemas import (
    AgentResponse,
    ConstraintResult,
    Plan,
)


# ── Session ─────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    """Request to create a new planning session."""
    user_id: Optional[str] = None


class SessionCreateResponse(BaseModel):
    """Response after creating a session."""
    session_id: str
    status: str = "active"


class SessionResponse(BaseModel):
    """Response with current session state."""
    session_id: str
    status: str
    state: Dict[str, Any]


class ProfileUpdate(BaseModel):
    """Private account and trip defaults editable by the signed-in user."""
    display_name: str = Field(default="", max_length=80)
    hometown: str = Field(default="", max_length=100)
    bio: str = Field(default="", max_length=500)
    languages: List[constr(strip_whitespace=True, max_length=40)] = Field(default_factory=list, max_length=12)
    interests: List[constr(strip_whitespace=True, max_length=40)] = Field(default_factory=list, max_length=20)
    default_travelers: int = Field(default=1, ge=1, le=20)
    preferred_currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    preferred_trip_style: str = Field(default="", max_length=80)


# ── Messages ────────────────────────────────────────────────────

class MessageContext(BaseModel):
    """
    Optional structured context sent by the UI with a message:
    the location picked in the search bar (or the user's current
    location) and the selected travel dates.
    """
    location: Optional[str] = Field(default=None, max_length=200)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    travelers: Optional[int] = Field(default=None, ge=1, le=50, description="Number of people travelling")
    explicit: bool = Field(
        default=False,
        description="True when the user picked these values for this very request "
                    "(search bar); False when it is only the ambient/default location.",
    )


class MessageRequest(BaseModel):
    """Request to send a message to the planning agent."""
    message: str = Field(min_length=1, max_length=2000, description="User's natural language message")
    context: Optional[MessageContext] = None
    request_id: Optional[str] = Field(
        default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
        description="Client-chosen id so the request can be cancelled (Stop button)",
    )


# ── Replan ──────────────────────────────────────────────────────

class ReplanRequest(BaseModel):
    """Request to replan with changed constraints."""
    changes: Dict[str, Any] = Field(
        description="Changed constraints, e.g. {'budget': 1500}"
    )


class ReplanResponse(BaseModel):
    """Response after replanning."""
    session_id: str
    status: str
    changes_applied: Dict[str, Any]
    plan: Optional[Plan] = None
    validation: Optional[ConstraintResult] = None
    message: str


# ── Health ──────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    service: str = "planwise-api"
    llm_available: bool = False
    llm_provider: str = ""
    llm_model: str = ""
    llm_chain: List[str] = Field(default_factory=list)
    llm_errors: Dict[str, str] = Field(
        default_factory=dict, description="Most recent failure per provider (to diagnose keys/models)"
    )
    limited_mode: bool = Field(
        default=False,
        description="True when only the keyless, rate-limited LLM endpoint is configured",
    )


# ── Geo ─────────────────────────────────────────────────────────

class PlaceResponse(BaseModel):
    """A geocoded place for the location picker."""
    name: str
    label: str
    display_name: str = ""
    lat: float
    lon: float
    country: str = ""
    country_code: str = ""
    currency: str = ""


# ── Plan ────────────────────────────────────────────────────────

class PlanResponse(BaseModel):
    """Response containing the current plan."""
    session_id: str
    plan: Optional[Plan] = None
    validation: Optional[ConstraintResult] = None


# ── Tool Search Requests ────────────────────────────────────────

class HotelSearchRequest(BaseModel):
    location: Optional[str] = None
    budget: Optional[float] = None
    preferences: List[str] = Field(default_factory=list)


class RestaurantSearchRequest(BaseModel):
    location: Optional[str] = None
    budget: Optional[float] = None
    preferences: List[str] = Field(default_factory=list)


class AttractionSearchRequest(BaseModel):
    location: Optional[str] = None
    interests: List[str] = Field(default_factory=list)


class TransportSearchRequest(BaseModel):
    location: Optional[str] = None
    source: Optional[str] = None
    destination: Optional[str] = None


# ── Error ───────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Consistent error response format from API doc Section 23."""
    error: ErrorDetail
