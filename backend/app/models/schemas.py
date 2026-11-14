"""
PlanWise AI - Core Pydantic Schemas

All structured data contracts for the planning agent system.
Based on the System Architecture document Section 8.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


def normalize_iso_date(value: Any) -> Optional[str]:
    """Return a YYYY-MM-DD string, or None when the value is not a real date."""
    if value in (None, "null", "None", ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


# ── Agent States ────────────────────────────────────────────────

class AgentStatus(str, Enum):
    """State machine states from Architecture doc Section 28."""
    RECEIVED = "received"
    UNDERSTANDING = "understanding"
    DECOMPOSING = "decomposing"
    EXECUTING = "executing"
    PLANNING = "planning"
    VALIDATING = "validating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    MISSING_INFORMATION = "missing_information"
    WAITING_FOR_USER = "waiting_for_user"
    CONSTRAINT_VIOLATION = "constraint_violation"
    REPLANNING = "replanning"
    ERROR = "error"


class ResponseStatus(str, Enum):
    """API response statuses from API doc Section 10."""
    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    REPLANNING = "replanning"
    CONSTRAINT_FAILURE = "constraint_failure"
    TOOL_FAILURE = "tool_failure"
    ERROR = "error"


# ── Intent & Understanding ──────────────────────────────────────

class IntentType(str, Enum):
    """Supported intent types from PRD FR-02."""
    HOTEL_SEARCH = "hotel_search"
    RESTAURANT_SEARCH = "restaurant_search"
    ATTRACTION_SEARCH = "attraction_search"
    TRANSPORT_SEARCH = "transport_search"
    TRIP_PLANNING = "trip_planning"
    STUDY_PLANNING = "study_planning"
    SCHEDULE_GENERATION = "schedule_generation"
    REPLANNING = "replanning"
    GENERAL_QUERY = "general_query"


class IntentResult(BaseModel):
    """Result of intent understanding from a user message."""
    intent: str = Field(description="Primary intent type")
    location: Optional[str] = Field(default=None, description="Target location")
    duration_days: Optional[int] = Field(default=None, description="Number of days")
    budget: Optional[float] = Field(default=None, description="Budget amount")
    preferences: List[str] = Field(default_factory=list, description="User preferences like vegetarian")
    interests: List[str] = Field(default_factory=list, description="User interests like culture, food")
    start_date: Optional[str] = Field(default=None, description="Trip start date, ISO YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="Trip end date, ISO YYYY-MM-DD")
    currency: Optional[str] = Field(default=None, description="ISO currency code the user mentioned")
    is_modification: bool = Field(default=False, description="True if modifying existing plan")
    raw_changes: Optional[Dict[str, Any]] = Field(default=None, description="Detected changes for replanning")

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def coerce_date(cls, v):
        return normalize_iso_date(v)

    @field_validator("currency", mode="before")
    @classmethod
    def coerce_currency(cls, v):
        if v in (None, "null", "None", ""):
            return None
        code = str(v).strip().upper()
        return code if len(code) == 3 and code.isalpha() else None

    @field_validator("raw_changes", mode="before")
    @classmethod
    def coerce_changes(cls, v):
        return v if isinstance(v, dict) and v else None

    @field_validator("is_modification", mode="before")
    @classmethod
    def coerce_bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "1")
        return bool(v)

    @field_validator("intent", mode="before")
    @classmethod
    def coerce_intent(cls, v):
        return str(v).strip().lower() if v else "general_query"

    @field_validator("preferences", "interests", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            clean = v.strip()
            return [clean] if clean and clean.lower() not in ("null", "none", "") else []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x not in (None, "null", "None", "")]
        return []

    @field_validator("location", mode="before")
    @classmethod
    def coerce_location(cls, v):
        if v in (None, "null", "None", ""):
            return None
        return str(v).strip()

    @field_validator("budget", mode="before")
    @classmethod
    def coerce_budget(cls, v):
        if v in (None, "null", "None", ""):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        import re
        clean = re.sub(r"[^\d.]", "", str(v))
        try:
            return float(clean) if clean else None
        except ValueError:
            return None

    @field_validator("duration_days", mode="before")
    @classmethod
    def coerce_duration(cls, v):
        if v in (None, "null", "None", ""):
            return None
        if isinstance(v, (int, float)):
            return int(v)
        import re
        clean = re.findall(r"\d+", str(v))
        return int(clean[0]) if clean else None


# ── Tasks ───────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Task(BaseModel):
    """A subtask generated from goal decomposition."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_type: str = Field(description="Type: search_hotels, search_restaurants, etc.")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    result: Optional[Any] = Field(default=None, description="Execution result")


# ── Tool Results ────────────────────────────────────────────────

class ToolResult(BaseModel):
    """Result from executing a domain tool."""
    tool_name: str
    success: bool
    results: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    query_used: Optional[str] = None


# ── Plan Structure ──────────────────────────────────────────────

class PlanActivity(BaseModel):
    """A single activity within a time slot."""
    name: str
    type: str = Field(default="activity", description="attraction, restaurant, transport, hotel, study")
    start_time: Optional[str] = Field(default=None, description="HH:MM (24h)")
    estimated_cost: Optional[float] = None
    duration_minutes: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("start_time", mode="before")
    @classmethod
    def coerce_start_time(cls, v):
        if v in (None, "null", "None", ""):
            return None
        import re
        match = re.search(r"(\d{1,2})[:.](\d{2})", str(v))
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if "pm" in str(v).lower() and hour < 12:
            hour += 12
        if hour > 23 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"

    @field_validator("details", mode="before")
    @classmethod
    def coerce_details(cls, v):
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            return {"description": v.strip()}
        return {}

    @field_validator("type", mode="before")
    @classmethod
    def coerce_type(cls, v):
        return str(v).strip().lower() if v else "activity"

    @field_validator("estimated_cost", mode="before")
    @classmethod
    def coerce_cost(cls, v):
        if v in (None, "null", "None", ""):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        str_v = str(v).strip().lower()
        if str_v in ("free", "0", "zero", "?", "unknown", "n/a"):
            return 0.0 if "free" in str_v or str_v == "0" else None
        import re
        clean = re.sub(r"[^\d.]", "", str_v)
        try:
            return float(clean) if clean else None
        except ValueError:
            return None

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def coerce_duration_minutes(cls, v):
        if v in (None, "null", "None", ""):
            return None
        if isinstance(v, (int, float)):
            return int(v)
        import re
        clean = re.findall(r"\d+", str(v))
        if clean:
            val = int(clean[0])
            if "hour" in str(v).lower():
                val *= 60
            return val
        return None


class PlanTimeSlot(BaseModel):
    """A time slot within a day (morning, afternoon, evening)."""
    time_of_day: str = Field(description="morning, afternoon, evening")
    activities: List[PlanActivity] = Field(default_factory=list)

    @field_validator("activities", mode="before")
    @classmethod
    def coerce_activities(cls, v):
        return v if isinstance(v, list) else []

    @field_validator("time_of_day", mode="before")
    @classmethod
    def coerce_time(cls, v):
        return str(v).strip().lower() if v else "morning"


class PlanDay(BaseModel):
    """A single day in the plan."""
    day: int
    date: Optional[str] = Field(default=None, description="Calendar date, ISO YYYY-MM-DD")
    slots: List[PlanTimeSlot] = Field(default_factory=list)


class Plan(BaseModel):
    """A complete generated plan."""
    summary: Optional[str] = Field(default=None, description="Short friendly overview")
    location: Optional[str] = None
    duration_days: int = 1
    days: List[PlanDay] = Field(default_factory=list)
    estimated_total_cost: Optional[float] = None
    currency: Optional[str] = Field(default=None, description="ISO currency code for all costs")
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    plan_type: str = Field(default="trip", description="trip or study")

    @field_validator("assumptions", mode="before")
    @classmethod
    def coerce_assumptions(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return [str(x) for x in v if x]

    @field_validator("duration_days", mode="before")
    @classmethod
    def coerce_duration(cls, v):
        try:
            return max(int(float(v)), 1)
        except (TypeError, ValueError):
            return 1

    @field_validator("plan_type", mode="before")
    @classmethod
    def coerce_plan_type(cls, v):
        return str(v).strip().lower() if v else "trip"

    @field_validator("estimated_total_cost", mode="before")
    @classmethod
    def coerce_total_cost(cls, v):
        if v in (None, "null", "None", ""):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        import re
        clean = re.sub(r"[^\d.]", "", str(v))
        try:
            return float(clean) if clean else None
        except ValueError:
            return None


# ── Validation ──────────────────────────────────────────────────

class ConstraintResult(BaseModel):
    """Result of constraint validation or plan verification."""
    valid: bool
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ── Plan State ──────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    """A single message in the conversation history."""
    role: str = Field(description="user or assistant")
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class PlanState(BaseModel):
    """Complete planning state for a session. Source of truth."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: Optional[str] = None
    intent: Optional[str] = None
    location: Optional[str] = None
    place: Optional[Dict[str, Any]] = Field(
        default=None, description="Geocoded place: name, lat, lon, country ..."
    )
    dates: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_days: Optional[int] = None
    budget: Optional[float] = None
    currency: Optional[str] = None
    preferences: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    subtasks: List[Task] = Field(default_factory=list)
    tool_results: List[ToolResult] = Field(default_factory=list)
    chosen_options: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Domain → list of selected records"
    )
    current_plan: Optional[Plan] = None
    violations: List[str] = Field(default_factory=list)
    conversation_history: List[ConversationMessage] = Field(default_factory=list)
    status: AgentStatus = Field(default=AgentStatus.RECEIVED)
    replan_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)


# ── Agent Response ──────────────────────────────────────────────

class AgentResponse(BaseModel):
    """Response returned from the planning agent to the API/frontend."""
    session_id: str
    status: ResponseStatus
    message: str
    plan: Optional[Plan] = None
    validation: Optional[ConstraintResult] = None
    intent: Optional[IntentResult] = None
    results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Structured search results for result cards"
    )
    results_domain: Optional[str] = None
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session context for the UI: location, dates, currency, data source",
    )
