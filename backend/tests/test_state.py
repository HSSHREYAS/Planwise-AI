"""
PlanWise AI - State Management Tests

Tests state creation, updates, preference retention, and change application.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.schemas import IntentResult, PlanState, ToolResult
from app.state.manager import StateManager


class TestStateCreation:
    def test_create_fresh_state(self, state_manager):
        state = state_manager.create_state()
        assert state.session_id
        assert state.location is None
        assert state.budget is None
        assert state.preferences == []
        assert state.tool_results == []

    def test_create_with_session_id(self, state_manager):
        state = state_manager.create_state(session_id="custom-123")
        assert state.session_id == "custom-123"


class TestUpdateFromIntent:
    def test_basic_update(self, empty_state, sample_intent):
        updated = StateManager.update_from_intent(empty_state, sample_intent)
        assert updated.location == "cambridge"
        assert updated.budget == 2000.0
        assert updated.duration_days == 2
        assert "vegetarian" in updated.preferences

    def test_preserves_existing_values(self, trip_state):
        # Intent with only budget change
        intent = IntentResult(intent="replanning", budget=1500.0)
        updated = StateManager.update_from_intent(trip_state, intent)
        assert updated.budget == 1500.0
        assert updated.location == "cambridge"  # preserved
        assert "vegetarian" in updated.preferences  # preserved

    def test_preferences_additive_no_duplicates(self, trip_state):
        intent = IntentResult(
            intent="trip_planning",
            preferences=["vegetarian", "budget-friendly"],
        )
        updated = StateManager.update_from_intent(trip_state, intent)
        assert "vegetarian" in updated.preferences
        assert "budget-friendly" in updated.preferences
        # No duplicates
        veg_count = sum(1 for p in updated.preferences if p == "vegetarian")
        assert veg_count == 1

    def test_interests_additive(self, empty_state):
        intent1 = IntentResult(intent="trip_planning", interests=["culture"])
        state = StateManager.update_from_intent(empty_state, intent1)
        intent2 = IntentResult(intent="trip_planning", interests=["food", "culture"])
        state = StateManager.update_from_intent(state, intent2)
        assert "culture" in state.interests
        assert "food" in state.interests
        culture_count = sum(1 for i in state.interests if i == "culture")
        assert culture_count == 1


class TestUpdateFromToolResult:
    def test_stores_tool_result(self, empty_state, sample_tool_result):
        updated = StateManager.update_from_tool_result(empty_state, sample_tool_result)
        assert len(updated.tool_results) == 1
        assert updated.tool_results[0].tool_name == "hotel_search"

    def test_updates_chosen_options(self, empty_state, sample_tool_result):
        updated = StateManager.update_from_tool_result(empty_state, sample_tool_result)
        assert "hotel" in updated.chosen_options
        assert len(updated.chosen_options["hotel"]) == 2

    def test_multiple_tool_results(self, empty_state, sample_tool_result, sample_restaurant_result):
        state = StateManager.update_from_tool_result(empty_state, sample_tool_result)
        state = StateManager.update_from_tool_result(state, sample_restaurant_result)
        assert len(state.tool_results) == 2
        assert "hotel" in state.chosen_options
        assert "restaurant" in state.chosen_options


class TestApplyChanges:
    def test_budget_change(self, trip_state):
        updated = StateManager.apply_changes(trip_state, {"budget": 1500})
        assert updated.budget == 1500.0
        assert updated.replan_count == 1

    def test_duration_change(self, trip_state):
        updated = StateManager.apply_changes(trip_state, {"duration_days": 3})
        assert updated.duration_days == 3

    def test_preference_change(self, trip_state):
        updated = StateManager.apply_changes(
            trip_state, {"preferences": ["vegan"]}
        )
        assert "vegan" in updated.preferences

    def test_multiple_changes(self, trip_state):
        updated = StateManager.apply_changes(
            trip_state, {"budget": 1000, "duration_days": 1}
        )
        assert updated.budget == 1000.0
        assert updated.duration_days == 1

    def test_replan_counter_increments(self, trip_state):
        assert trip_state.replan_count == 0
        StateManager.apply_changes(trip_state, {"budget": 1500})
        assert trip_state.replan_count == 1
        StateManager.apply_changes(trip_state, {"budget": 1000})
        assert trip_state.replan_count == 2


class TestConversationSummary:
    def test_empty_state_summary(self, empty_state):
        summary = StateManager.get_conversation_summary(empty_state)
        assert "No state" in summary

    def test_populated_state_summary(self, trip_state):
        summary = StateManager.get_conversation_summary(trip_state)
        assert "cambridge" in summary.lower()
        assert "2000" in summary
        assert "vegetarian" in summary

    def test_state_summary(self, trip_state):
        summary = StateManager.get_state_summary(trip_state)
        assert "cambridge" in summary.lower()
        assert "Budget" in summary


class TestAddMessage:
    def test_add_user_message(self, empty_state):
        updated = StateManager.add_message(empty_state, "user", "Hello")
        assert len(updated.conversation_history) == 1
        assert updated.conversation_history[0].role == "user"

    def test_add_multiple_messages(self, empty_state):
        state = StateManager.add_message(empty_state, "user", "Plan a trip")
        state = StateManager.add_message(state, "assistant", "Sure!")
        assert len(state.conversation_history) == 2
