"""
Unit tests for tools, registry, agent intent/decomposition, and schema pre-validators.
Tests all bug resolutions.
"""

import pytest
from app.models.schemas import (
    IntentResult,
    PlanActivity,
    Plan,
    PlanState,
    Task,
)
from app.tools.registry import TOOL_REGISTRY, execute_tool, get_available_tools
from app.agent.planner import PlanningAgent
from app.retrieval.index_manager import get_all_records


class TestToolRegistry:
    """Test tool registry initialization."""

    def test_all_tools_registered(self):
        tools = get_available_tools()
        expected = ["hotel_search", "restaurant_search", "attraction_search", "transport_search"]
        for tool in expected:
            assert tool in tools


class TestToolExecution:
    """Test tool execution with various parameter formats."""

    def test_hotel_search_numeric_budget(self):
        result = execute_tool("hotel_search", {"location": "centre", "budget": 1000})
        assert result.success is True
        assert isinstance(result.results, list)

    def test_hotel_search_string_preferences(self):
        result = execute_tool("hotel_search", {"location": "centre", "preferences": "parking"})
        assert result.success is True
        assert isinstance(result.results, list)

    def test_restaurant_search_numeric_budget(self):
        result = execute_tool("restaurant_search", {"location": "centre", "budget": 500})
        assert result.success is True
        assert isinstance(result.results, list)

    def test_restaurant_search_string_preferences(self):
        result = execute_tool("restaurant_search", {"location": "centre", "preferences": "vegetarian"})
        assert result.success is True
        assert isinstance(result.results, list)

    def test_attraction_search_string_interests(self):
        result = execute_tool("attraction_search", {"location": "centre", "interests": "museum"})
        assert result.success is True
        assert len(result.results) > 0


class TestAgentDecompositionAndIntent:
    """Test agent intent fallback and deterministic decomposition."""

    def test_fallback_intent_budget_vs_duration(self):
        agent = PlanningAgent()
        state = PlanState()
        res = agent._fallback_intent("Plan a 2 day trip to Cambridge", state)
        assert res.duration_days == 2
        assert res.budget is None  # Must NOT capture '2' as budget!
        assert res.location == "cambridge"

    def test_fallback_intent_with_explicit_budget(self):
        agent = PlanningAgent()
        state = PlanState()
        res = agent._fallback_intent("Plan a 3-day trip to Cambridge with budget of 2500", state)
        assert res.duration_days == 3
        assert res.budget == 2500.0
        assert res.location == "cambridge"

    def test_single_domain_decomposition(self):
        agent = PlanningAgent()
        state = PlanState(intent="hotel_search", location="cambridge")
        tasks = agent._decompose(state)
        assert len(tasks) == 1
        assert tasks[0].task_type == "hotel_search"

    def test_restaurant_single_domain_decomposition(self):
        agent = PlanningAgent()
        state = PlanState(intent="restaurant_search", location="cambridge")
        tasks = agent._decompose(state)
        assert len(tasks) == 1
        assert tasks[0].task_type == "restaurant_search"


class TestSchemaCoercion:
    """Test pre-validators on schemas."""

    def test_intent_result_null_coercion(self):
        res = IntentResult(
            intent="trip_planning",
            preferences=None,
            interests=None,
            location="null",
            budget="1500",
            duration_days="2 days",
        )
        assert res.preferences == []
        assert res.interests == []
        assert res.location is None
        assert res.budget == 1500.0
        assert res.duration_days == 2

    def test_plan_activity_cost_coercion(self):
        act1 = PlanActivity(name="Museum", type="attraction", estimated_cost="free")
        assert act1.estimated_cost == 0.0

        act2 = PlanActivity(name="Dinner", type="restaurant", estimated_cost="£35.50")
        assert act2.estimated_cost == 35.50


class TestRetrievalFallback:
    """Test retrieval index manager fallback data loading."""

    def test_transport_fallback_filename(self):
        records = get_all_records("transport")
        assert isinstance(records, list)
        assert len(records) > 0
