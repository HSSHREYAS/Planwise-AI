"""
PlanWise AI - Hotel Search Tool

Searches local MultiWOZ-derived hotel data.
Never fabricates results.
"""

import logging
from typing import List, Optional

from app.models.schemas import ToolResult
from app.retrieval.search import retrieval_service
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def search_hotel(
    location: Optional[str] = None,
    budget: Optional[str] = None,
    preferences: Optional[List[str]] = None,
) -> ToolResult:
    """
    Search for hotels matching the given criteria.

    Args:
        location: Target area/location
        budget: Price range preference (cheap, moderate, expensive)
        preferences: List of preferences (e.g., parking, internet)

    Returns:
        ToolResult with matching hotel records
    """
    # Normalize preferences to list of strings
    pref_list: List[str] = []
    if preferences:
        if isinstance(preferences, str):
            pref_list = [preferences.strip()] if preferences.strip() else []
        elif isinstance(preferences, list):
            pref_list = [str(p).strip() for p in preferences if p]

    # Build search query
    query_parts = ["hotel"]
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
        # Map budget descriptions or numeric values to MultiWOZ pricerange values
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

    # Map amenity preferences
    for p in pref_list:
        p_lower = p.lower()
        if "parking" in p_lower:
            filters["parking"] = "yes"
        if "internet" in p_lower or "wifi" in p_lower:
            filters["internet"] = "yes"
        if "guesthouse" in p_lower:
            filters["type"] = "guesthouse"

    # Search using retrieval service
    results = retrieval_service.search(
        domain="hotel",
        query=query,
        filters=filters,
        top_k=5,
    )

    return ToolResult(
        tool_name="hotel_search",
        success=True,
        results=results,
        query_used=query,
    )


# Register this tool
register_tool("hotel_search", search_hotel)
