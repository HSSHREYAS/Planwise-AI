"""
PlanWise AI - API Request/Response Models

Pydantic models for API layer validation.
Based on API Specific Document Sections 7-17, 22.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

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


# ── Messages ────────────────────────────────────────────────────

class MessageRequest(BaseModel):
    """Request to send a message to the planning agent."""
    message: str = Field(min_length=1, description="User's natural language message")


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
    ollama_available: bool = False


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
