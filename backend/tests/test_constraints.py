"""
PlanWise AI - Constraint Engine Tests

Tests deterministic constraint validation: budget, duration,
preferences, impossible constraints.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.schemas import (
    Plan,
    PlanActivity,
    PlanDay,
    PlanState,
    PlanTimeSlot,
)
from app.validation.constraints import (
    check_budget,
    check_duration,
    check_impossible_constraints,
    check_preferences,
    check_required_components,
    validate_plan,
)


class TestBudgetCheck:
    def test_within_budget(self, sample_plan, trip_state):
        violations = check_budget(sample_plan, trip_state.budget)
        assert violations == []

    def test_exceeds_budget(self, sample_plan):
        sample_plan.estimated_total_cost = 5000.0
        violations = check_budget(sample_plan, 2000.0)
        assert len(violations) == 1
        assert "exceeds" in violations[0].lower()

    def test_no_budget_set(self, sample_plan):
        violations = check_budget(sample_plan, None)
        assert violations == []

    def test_no_cost_estimated(self):
        plan = Plan(duration_days=1, estimated_total_cost=None)
        violations = check_budget(plan, 2000.0)
        assert violations == []

    def test_exactly_at_budget(self, sample_plan):
        sample_plan.estimated_total_cost = 2000.0
        violations = check_budget(sample_plan, 2000.0)
        assert violations == []


class TestDurationCheck:
    def test_correct_duration(self, sample_plan, trip_state):
        violations = check_duration(sample_plan, trip_state.duration_days)
        assert violations == []

    def test_wrong_duration(self, sample_plan):
        violations = check_duration(sample_plan, 3)  # Plan has 2 days
        assert len(violations) == 1
        assert "day" in violations[0].lower()

    def test_no_duration_set(self, sample_plan):
        violations = check_duration(sample_plan, None)
        assert violations == []


class TestPreferenceCheck:
    def test_no_preferences(self, sample_plan):
        violations = check_preferences(sample_plan, [])
        assert violations == []

    def test_vegetarian_preference_respected(self, sample_plan):
        # Plan has "The Golden Curry" (indian) and "Veggie Garden" (vegetarian)
        violations = check_preferences(sample_plan, ["vegetarian"])
        # Neither name contains explicit non-veg indicators
        assert violations == []

    def test_non_vegetarian_restaurant_flagged(self):
        plan = Plan(
            duration_days=1,
            days=[
                PlanDay(
                    day=1,
                    slots=[
                        PlanTimeSlot(
                            time_of_day="evening",
                            activities=[
                                PlanActivity(
                                    name="Bob's Steakhouse",
                                    type="restaurant",
                                    details={"food": "steakhouse"},
                                )
                            ],
                        )
                    ],
                )
            ],
        )
        violations = check_preferences(plan, ["vegetarian"])
        assert len(violations) == 1
        assert "steakhouse" in violations[0].lower() or "vegetarian" in violations[0].lower()


class TestRequiredComponents:
    def test_trip_has_activities(self, sample_plan):
        violations = check_required_components(sample_plan, "trip_planning")
        assert violations == []

    def test_empty_trip_plan(self):
        plan = Plan(duration_days=1, days=[PlanDay(day=1, slots=[])])
        violations = check_required_components(plan, "trip_planning")
        assert len(violations) >= 1

    def test_non_trip_no_check(self):
        plan = Plan(duration_days=1, days=[])
        violations = check_required_components(plan, "study_planning")
        assert violations == []


class TestImpossibleConstraints:
    def test_tight_budget_warning(self):
        state = PlanState(budget=400.0, duration_days=2)
        warnings = check_impossible_constraints(state)
        assert len(warnings) >= 1
        assert "tight" in warnings[0].lower() or "low" in warnings[0].lower()

    def test_reasonable_budget_no_warning(self):
        state = PlanState(budget=5000.0, duration_days=2)
        warnings = check_impossible_constraints(state)
        budget_warnings = [w for w in warnings if "budget" in w.lower() or "tight" in w.lower()]
        assert budget_warnings == []

    def test_no_budget_no_warning(self):
        state = PlanState(duration_days=2)
        warnings = check_impossible_constraints(state)
        budget_warnings = [w for w in warnings if "budget" in w.lower()]
        assert budget_warnings == []


class TestValidatePlan:
    def test_valid_plan(self, sample_plan, trip_state):
        result = validate_plan(sample_plan, trip_state)
        assert result.valid is True
        assert result.violations == []

    def test_budget_violation(self, over_budget_plan, trip_state):
        result = validate_plan(over_budget_plan, trip_state)
        assert result.valid is False
        assert any("exceed" in v.lower() for v in result.violations)

    def test_duration_violation(self, wrong_duration_plan, trip_state):
        result = validate_plan(wrong_duration_plan, trip_state)
        assert result.valid is False
        assert any("day" in v.lower() for v in result.violations)

    def test_multiple_violations(self, over_budget_plan, trip_state):
        over_budget_plan.days = over_budget_plan.days[:1]  # Wrong duration too
        result = validate_plan(over_budget_plan, trip_state)
        assert result.valid is False
        assert len(result.violations) >= 2
