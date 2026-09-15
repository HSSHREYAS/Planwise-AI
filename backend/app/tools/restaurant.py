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
    # Normalize preferences to list of strings
    pref_list: List[str] = []
    if preferences:
        if isinstance(preferences, str):
            pref_list = [preferences.strip()] if preferences.strip() else []
        elif isinstance(preferences, list):
            pref_list = [str(p).strip() for p in preferences if p]

    # Build search query
    query_parts = ["restaurant"]
    if location:
        query_parts.append(str(location).strip())
    if budget is not None:
        query_parts.append(str(budget).strip())
    if pref_list:
        query_parts.extend(pref_list)
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
    if budget is not None:
        budget_str = str(budget).lower().strip()
        if any(w in budget_str for w in ["cheap", "budget", "low", "inexpensive"]):
            filters["pricerange"] = "cheap"
        elif any(w in budget_str for w in ["moderate", "medium", "mid"]):
            filters["pricerange"] = "moderate"
        elif any(w in budget_str for w in ["expensive", "luxury", "high"]):
            filters["pricerange"] = "expensive"
        else:
            import re
            num_match = re.search(r"[\d.]+", budget_str)
            if num_match:
                try:
                    num_val = float(num_match.group(0))
                    if num_val < 500:
                        filters["pricerange"] = "cheap"
                    elif num_val <= 1500:
                        filters["pricerange"] = "moderate"
                    else:
                        filters["pricerange"] = "expensive"
                except ValueError:
                    pass
    if pref_list:
        # Check for food type preferences against actual MultiWOZ cuisines
        cuisines = [
            "indian", "chinese", "italian", "thai", "japanese", "mexican",
            "british", "european", "african", "korean", "turkish", "portuguese",
            "seafood", "french", "spanish", "mediterranean", "lebanese", "vietnamese",
        ]
        for pref in pref_list:
            pref_lower = pref.lower()
            if pref_lower in cuisines:
                filters["food"] = pref_lower
                break

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
