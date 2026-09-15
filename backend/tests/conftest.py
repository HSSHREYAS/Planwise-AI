"""
PlanWise AI - Test Fixtures

Shared pytest fixtures for all test modules.
"""

import sys
from pathlib import Path

import pytest

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.schemas import (
    AgentStatus,
    ConstraintResult,
    IntentResult,
    Plan,
    PlanActivity,
    PlanDay,
    PlanState,
    PlanTimeSlot,
    Task,
    ToolResult,
)
from app.state.manager import StateManager


@pytest.fixture
def state_manager():
    """Fresh StateManager instance."""
    return StateManager()


@pytest.fixture
def empty_state():
    """Empty PlanState for testing."""
    return StateManager.create_state(session_id="test-session-001")


@pytest.fixture
def trip_state():
    """PlanState pre-filled with trip planning data."""
    state = StateManager.create_state(session_id="test-session-002")
    state.intent = "trip_planning"
    state.location = "cambridge"
    state.duration_days = 2
    state.budget = 2000.0
    state.preferences = ["vegetarian"]
    state.interests = ["culture", "food"]
    return state


@pytest.fixture
def sample_intent():
    """Sample IntentResult for testing."""
    return IntentResult(
        intent="trip_planning",
        location="cambridge",
        duration_days=2,
        budget=2000.0,
        preferences=["vegetarian"],
        interests=["culture", "food"],
        is_modification=False,
    )


@pytest.fixture
def sample_tool_result():
    """Sample ToolResult with hotel data."""
    return ToolResult(
        tool_name="hotel_search",
        success=True,
        results=[
            {"name": "Alpha Hotel", "area": "centre", "pricerange": "moderate", "stars": "3"},
            {"name": "Beta Guesthouse", "area": "north", "pricerange": "cheap", "stars": "2"},
        ],
        query_used="hotel cambridge moderate",
    )


@pytest.fixture
def sample_restaurant_result():
    """Sample ToolResult with restaurant data."""
    return ToolResult(
        tool_name="restaurant_search",
        success=True,
        results=[
            {"name": "The Golden Curry", "area": "centre", "food": "indian", "pricerange": "moderate"},
            {"name": "Veggie Garden", "area": "south", "food": "vegetarian", "pricerange": "cheap"},
        ],
        query_used="restaurant cambridge vegetarian",
    )


@pytest.fixture
def sample_attraction_result():
    """Sample ToolResult with attraction data."""
    return ToolResult(
        tool_name="attraction_search",
        success=True,
        results=[
            {"name": "Kings College", "area": "centre", "type": "college", "entrance_fee": "free"},
            {"name": "Fitzwilliam Museum", "area": "west", "type": "museum", "entrance_fee": "free"},
            {"name": "Cambridge Park", "area": "east", "type": "park", "entrance_fee": "free"},
        ],
        query_used="attraction cambridge culture",
    )


@pytest.fixture
def sample_plan():
    """Sample Plan for testing."""
    return Plan(
        location="cambridge",
        duration_days=2,
        days=[
            PlanDay(
                day=1,
                slots=[
                    PlanTimeSlot(
                        time_of_day="morning",
                        activities=[
                            PlanActivity(
                                name="Kings College",
                                type="attraction",
                                estimated_cost=0,
                                details={"type": "college"},
                            )
                        ],
                    ),
                    PlanTimeSlot(
                        time_of_day="afternoon",
                        activities=[
                            PlanActivity(
                                name="Fitzwilliam Museum",
                                type="attraction",
                                estimated_cost=0,
                                details={"type": "museum"},
                            )
                        ],
                    ),
                    PlanTimeSlot(
                        time_of_day="evening",
                        activities=[
                            PlanActivity(
                                name="The Golden Curry",
                                type="restaurant",
                                estimated_cost=500,
                                details={"food": "indian"},
                            )
                        ],
                    ),
                ],
            ),
            PlanDay(
                day=2,
                slots=[
                    PlanTimeSlot(
                        time_of_day="morning",
                        activities=[
                            PlanActivity(
                                name="Cambridge Park",
                                type="attraction",
                                estimated_cost=0,
                                details={"type": "park"},
                            )
                        ],
                    ),
                    PlanTimeSlot(
                        time_of_day="afternoon",
                        activities=[
                            PlanActivity(
                                name="Alpha Hotel",
                                type="hotel",
                                estimated_cost=800,
                                details={},
                            )
                        ],
                    ),
                    PlanTimeSlot(
                        time_of_day="evening",
                        activities=[
                            PlanActivity(
                                name="Veggie Garden",
                                type="restaurant",
                                estimated_cost=200,
                                details={"food": "vegetarian"},
                            )
                        ],
                    ),
                ],
            ),
        ],
        estimated_total_cost=1500.0,
        assumptions=["Prices are estimates based on available data"],
    )


@pytest.fixture
def over_budget_plan(sample_plan):
    """Plan that exceeds a typical budget."""
    plan = sample_plan.model_copy(deep=True)
    plan.estimated_total_cost = 5000.0
    return plan


@pytest.fixture
def wrong_duration_plan(sample_plan):
    """Plan with wrong number of days."""
    plan = sample_plan.model_copy(deep=True)
    plan.days = plan.days[:1]  # Only 1 day instead of 2
    return plan
