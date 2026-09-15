"""
PlanWise AI - Constraint Engine

Deterministic constraint validation in Python.
The LLM is NEVER responsible for budget arithmetic or rule checking.
Based on Architecture doc Section 12.
"""

import logging
from typing import List, Optional

from app.models.schemas import (
    ConstraintResult,
    Plan,
    PlanState,
)

logger = logging.getLogger(__name__)


def check_budget(plan: Plan, budget: Optional[float]) -> List[str]:
    """Check if estimated plan cost exceeds budget."""
    violations = []
    if budget is None or plan.estimated_total_cost is None:
        return violations

    if plan.estimated_total_cost > budget:
        violations.append(
            f"Estimated cost ₹{plan.estimated_total_cost:.0f} "
            f"exceeds budget ₹{budget:.0f}"
        )
    return violations


def check_duration(plan: Plan, duration_days: Optional[int]) -> List[str]:
    """Check if plan duration matches requested duration."""
    violations = []
    if duration_days is None:
        return violations

    if len(plan.days) != duration_days:
        violations.append(
            f"Plan has {len(plan.days)} day(s) but "
            f"{duration_days} day(s) were requested"
        )
    return violations


def check_preferences(plan: Plan, preferences: List[str]) -> List[str]:
    """Check if plan respects stated user preferences."""
    violations = []
    if not preferences:
        return violations

    # Collect all restaurant activities
    restaurant_activities = []
    for day in plan.days:
        for slot in day.slots:
            for activity in slot.activities:
                if activity.type == "restaurant":
                    restaurant_activities.append(activity)

    # Check vegetarian preference
    if "vegetarian" in preferences and restaurant_activities:
        for activity in restaurant_activities:
            food_type = activity.details.get("food", "").lower()
            name_lower = activity.name.lower()
            # Flag if explicitly non-vegetarian
            non_veg_indicators = [
                "steakhouse", "bbq", "grill", "seafood",
                "meat", "chicken", "pork", "beef"
            ]
            for indicator in non_veg_indicators:
                if indicator in food_type or indicator in name_lower:
                    violations.append(
                        f"Restaurant '{activity.name}' may not be vegetarian "
                        f"(user preference: vegetarian)"
                    )
                    break

    return violations


def check_required_components(
    plan: Plan, intent: Optional[str]
) -> List[str]:
    """Check that the plan has required components for its type."""
    violations = []
    if intent is None:
        return violations

    if intent == "trip_planning":
        # Trip plans should have at least some activities
        total_activities = sum(
            len(activity.activities)
            for day in plan.days
            for activity in day.slots
        )
        if total_activities == 0:
            violations.append("Trip plan has no activities")

        # Check that each day has at least one activity
        for day in plan.days:
            day_activities = sum(len(s.activities) for s in day.slots)
            if day_activities == 0:
                violations.append(f"Day {day.day} has no activities")

    return violations


def check_impossible_constraints(state: PlanState) -> List[str]:
    """
    Detect obviously unrealistic constraint combinations.
    Called before plan generation to catch issues early.
    """
    warnings = []

    if state.budget is not None and state.duration_days is not None:
        # Very rough heuristic: < 500 per day is extremely tight
        per_day = state.budget / max(state.duration_days, 1)
        if per_day < 300:
            warnings.append(
                f"Budget of ₹{state.budget:.0f} for {state.duration_days} "
                f"day(s) (₹{per_day:.0f}/day) is very tight and may not "
                f"allow for a complete plan"
            )

    # Count requested attractions if mentioned
    if state.interests and state.budget is not None:
        if len(state.interests) > 5 and state.budget < 1000:
            warnings.append(
                "Many interests with a limited budget may result in an "
                "incomplete plan"
            )

    return warnings


def validate_plan(plan: Plan, state: PlanState) -> ConstraintResult:
    """
    Run all deterministic constraint checks on a candidate plan.

    Returns:
        ConstraintResult with valid flag, violations, and warnings.
    """
    violations: List[str] = []
    warnings: List[str] = []

    # Run each check
    violations.extend(check_budget(plan, state.budget))
    violations.extend(check_duration(plan, state.duration_days))
    violations.extend(check_preferences(plan, state.preferences))
    violations.extend(check_required_components(plan, state.intent))

    # Also check for impossible constraints as warnings
    warnings.extend(check_impossible_constraints(state))

    result = ConstraintResult(
        valid=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )

    if violations:
        logger.warning(f"Plan validation failed: {violations}")
    else:
        logger.info("Plan validation passed")

    return result
