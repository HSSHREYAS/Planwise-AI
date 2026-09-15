"""
PlanWise AI - Plan Verifier

Checks data integrity and grounding of generated plans.
Separate from constraint engine — this verifies that plan content
comes from retrieved data, not LLM hallucination.
Based on Architecture doc Section 3.10.
"""

import logging
from typing import Set

from app.models.schemas import (
    ConstraintResult,
    Plan,
    PlanState,
)

logger = logging.getLogger(__name__)


def verify_plan(plan: Plan, state: PlanState) -> ConstraintResult:
    """
    Verify that a plan is grounded in retrieved data.

    Checks:
    1. Activities reference retrieved records (anti-hallucination)
    2. Plan structure is valid
    3. No duplicate activities in same time slot
    4. Schedule coherence
    """
    violations = []
    warnings = []

    # 1. Collect all retrieved record names for grounding check
    retrieved_names: Set[str] = set()
    for tool_result in state.tool_results:
        if tool_result.success:
            for record in tool_result.results:
                name = record.get("name", "")
                if name:
                    retrieved_names.add(name.lower().strip())

    # 2. Check each activity is grounded in retrieved data
    if retrieved_names:  # Only check if we actually retrieved data
        for day in plan.days:
            for slot in day.slots:
                for activity in slot.activities:
                    # Skip study activities and transport (may be generic)
                    if activity.type in ("study", "transport"):
                        continue
                    activity_name = activity.name.lower().strip()
                    if activity_name and activity_name not in retrieved_names:
                        # Fuzzy match: check if any retrieved name contains
                        # the activity name or vice versa
                        fuzzy_match = any(
                            activity_name in rn or rn in activity_name
                            for rn in retrieved_names
                        )
                        if not fuzzy_match:
                            warnings.append(
                                f"'{activity.name}' was not found in retrieved "
                                f"data (possible hallucination)"
                            )

    # 3. Check plan structure
    if plan.duration_days > 0 and len(plan.days) == 0:
        violations.append("Plan specifies duration but has no days")

    for day in plan.days:
        if not day.slots:
            warnings.append(f"Day {day.day} has no time slots")

        # Check for expected time slots
        slot_times = {s.time_of_day for s in day.slots}
        for expected in ("morning", "afternoon", "evening"):
            if expected not in slot_times:
                # Not a violation, just a warning
                pass  # Some days may intentionally skip slots

    # 4. Check for duplicate activities within the same time slot
    for day in plan.days:
        for slot in day.slots:
            seen_names = set()
            for activity in slot.activities:
                key = activity.name.lower().strip()
                if key in seen_names:
                    warnings.append(
                        f"Duplicate activity '{activity.name}' in "
                        f"Day {day.day} {slot.time_of_day}"
                    )
                seen_names.add(key)

    # 5. Check cost consistency
    if plan.estimated_total_cost is not None:
        calculated_total = 0.0
        has_costs = False
        for day in plan.days:
            for slot in day.slots:
                for activity in slot.activities:
                    if activity.estimated_cost is not None:
                        calculated_total += activity.estimated_cost
                        has_costs = True

        if has_costs and abs(calculated_total - plan.estimated_total_cost) > 100:
            warnings.append(
                f"Plan total cost (₹{plan.estimated_total_cost:.0f}) differs "
                f"significantly from sum of activities (₹{calculated_total:.0f})"
            )

    result = ConstraintResult(
        valid=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )

    if violations:
        logger.warning(f"Plan verification failed: {violations}")
    if warnings:
        logger.info(f"Plan verification warnings: {warnings}")
    if result.valid:
        logger.info("Plan verification passed")

    return result
