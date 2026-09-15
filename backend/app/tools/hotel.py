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
    # Build search query
    query_parts = ["hotel"]
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
        # Map budget descriptions to MultiWOZ pricerange values
        budget_lower = str(budget).lower()
        if any(w in budget_lower for w in ["cheap", "budget", "low", "inexpensive"]):
            filters["pricerange"] = "cheap"
        elif any(w in budget_lower for w in ["moderate", "medium", "mid"]):
            filters["pricerange"] = "moderate"
        elif any(w in budget_lower for w in ["expensive", "luxury", "high"]):
            filters["pricerange"] = "expensive"

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
