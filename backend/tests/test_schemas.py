"""
PlanWise AI - Schema Tests

Tests Pydantic model construction, serialization, and defaults.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.schemas import (
    AgentResponse,
    AgentStatus,
    ConstraintResult,
    ConversationMessage,
    IntentResult,
    IntentType,
    Plan,
    PlanActivity,
    PlanDay,
    PlanState,
    PlanTimeSlot,
    ResponseStatus,
    Task,
    TaskStatus,
    ToolResult,
)


class TestIntentResult:
    def test_create_minimal(self):
        intent = IntentResult(intent="trip_planning")
        assert intent.intent == "trip_planning"
        assert intent.location is None
        assert intent.preferences == []
        assert intent.is_modification is False

    def test_create_full(self):
        intent = IntentResult(
            intent="trip_planning",
            location="cambridge",
            duration_days=2,
            budget=2000.0,
            preferences=["vegetarian"],
            interests=["culture"],
            is_modification=False,
        )
        assert intent.location == "cambridge"
        assert intent.budget == 2000.0
        assert "vegetarian" in intent.preferences

    def test_serialization(self):
        intent = IntentResult(intent="hotel_search", location="london")
        data = intent.model_dump()
        assert data["intent"] == "hotel_search"
        assert data["location"] == "london"

    def test_from_dict(self):
        data = {"intent": "restaurant_search", "preferences": ["indian"]}
        intent = IntentResult.model_validate(data)
        assert intent.intent == "restaurant_search"
        assert "indian" in intent.preferences


class TestTask:
    def test_create_with_defaults(self):
        task = Task(task_type="search_hotels", parameters={"location": "cambridge"})
        assert task.status == TaskStatus.PENDING
        assert task.task_id  # auto-generated
        assert task.parameters["location"] == "cambridge"

    def test_serialization(self):
        task = Task(task_type="search_restaurants", parameters={})
        data = task.model_dump()
        assert data["task_type"] == "search_restaurants"
        assert data["status"] == "pending"


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(
            tool_name="hotel_search",
            success=True,
            results=[{"name": "Test Hotel"}],
        )
        assert result.success is True
        assert len(result.results) == 1

    def test_failure_result(self):
        result = ToolResult(
            tool_name="hotel_search",
            success=False,
            error="No results found",
        )
        assert result.success is False
        assert result.error == "No results found"
        assert result.results == []


class TestPlan:
    def test_create_empty_plan(self):
        plan = Plan(duration_days=1)
        assert plan.days == []
        assert plan.estimated_total_cost is None

    def test_create_full_plan(self, sample_plan):
        assert sample_plan.location == "cambridge"
        assert sample_plan.duration_days == 2
        assert len(sample_plan.days) == 2
        assert sample_plan.estimated_total_cost == 1500.0

    def test_plan_structure(self, sample_plan):
        day1 = sample_plan.days[0]
        assert day1.day == 1
        assert len(day1.slots) == 3
        morning = day1.slots[0]
        assert morning.time_of_day == "morning"
        assert len(morning.activities) == 1
        assert morning.activities[0].name == "Kings College"


class TestPlanState:
    def test_create_default_state(self):
        state = PlanState()
        assert state.session_id  # auto-generated
        assert state.status == AgentStatus.RECEIVED
        assert state.preferences == []
        assert state.tool_results == []
        assert state.current_plan is None

    def test_state_with_data(self):
        state = PlanState(
            location="cambridge",
            duration_days=2,
            budget=2000.0,
            preferences=["vegetarian"],
        )
        assert state.location == "cambridge"
        assert state.budget == 2000.0

    def test_serialization_roundtrip(self):
        state = PlanState(location="london", budget=1000.0)
        data = state.model_dump()
        restored = PlanState.model_validate(data)
        assert restored.location == "london"
        assert restored.budget == 1000.0


class TestConstraintResult:
    def test_valid(self):
        result = ConstraintResult(valid=True)
        assert result.violations == []
        assert result.warnings == []

    def test_with_violations(self):
        result = ConstraintResult(
            valid=False,
            violations=["Budget exceeded"],
            warnings=["Low budget per day"],
        )
        assert not result.valid
        assert len(result.violations) == 1
        assert len(result.warnings) == 1


class TestAgentResponse:
    def test_completed_response(self):
        response = AgentResponse(
            session_id="test-123",
            status=ResponseStatus.COMPLETED,
            message="Here is your plan.",
        )
        assert response.status == ResponseStatus.COMPLETED
        assert response.plan is None

    def test_error_response(self):
        response = AgentResponse(
            session_id="test-123",
            status=ResponseStatus.ERROR,
            message="Something went wrong.",
        )
        assert response.status == ResponseStatus.ERROR
