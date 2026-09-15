"""
PlanWise AI - Restaurant Search Tool

Searches local MultiWOZ-derived restaurant data.
Never fabricates results.
"""

import logging
from typing import List, Optional

from app.models.schemas import ToolResult
from app.retrieval.search import retrieval_service
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def search_restaurant(
    location: Optional[str] = None,
    budget: Optional[str] = None,
    preferences: Optional[List[str]] = None,
) -> ToolResult:
    """
    Search for restaurants matching the given criteria.

    Args:
        location: Target area/location
        budget: Price range preference
        preferences: Dietary preferences (e.g., vegetarian, indian)

    Returns:
        ToolResult with matching restaurant records
    """
    # Build search query
    query_parts = ["restaurant"]
    if location:
        query_parts.append(location)
    if budget:
        query_parts.append(budget)
    if preferences:
        query_parts.extend(preferences)
    query = " ".join(query_parts)

    # Build metadata filters
    filters = {}
    valid_areas = {"centre", "south", "north", "east", "west"}
    if location:
        loc_lower = str(location).lower().strip()
        if loc_lower in valid_areas:
            filters["area"] = loc_lower
        else:
            for a in valid_areas:
                if a in loc_lower:
                    filters["area"] = a
                    break
    if budget:
        budget_lower = str(budget).lower()
        if any(w in budget_lower for w in ["cheap", "budget", "low", "inexpensive"]):
            filters["pricerange"] = "cheap"
        elif any(w in budget_lower for w in ["moderate", "medium", "mid"]):
            filters["pricerange"] = "moderate"
        elif any(w in budget_lower for w in ["expensive", "luxury", "high"]):
            filters["pricerange"] = "expensive"
    if preferences:
        # Check for food type preferences
        for pref in preferences:
            pref_lower = pref.lower()
            if pref_lower in [
                "vegetarian", "indian", "chinese", "italian", "thai",
                "japanese", "mexican", "british", "european", "african",
                "korean", "turkish", "portuguese", "seafood",
            ]:
                filters["food"] = pref_lower

    # Search
    results = retrieval_service.search(
        domain="restaurant",
        query=query,
        filters=filters,
        top_k=5,
    )

    return ToolResult(
        tool_name="restaurant_search",
        success=True,
        results=results,
        query_used=query,
    )


# Register this tool
register_tool("restaurant_search", search_restaurant)
