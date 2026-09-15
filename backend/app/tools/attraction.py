"""
PlanWise AI - Attraction Search Tool

Searches local MultiWOZ-derived attraction data.
Never fabricates results.
"""

import logging
from typing import List, Optional

from app.models.schemas import ToolResult
from app.retrieval.search import retrieval_service
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def search_attraction(
    location: Optional[str] = None,
    interests: Optional[List[str]] = None,
) -> ToolResult:
    """
    Search for attractions matching the given criteria.

    Args:
        location: Target area/location
        interests: Interest categories (e.g., museum, park, architecture)

    Returns:
        ToolResult with matching attraction records
    """
    # Build search query
    query_parts = ["attraction"]
    if location:
        query_parts.append(location)
    if interests:
        query_parts.extend(interests)
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
    if interests:
        # Map interests to MultiWOZ attraction types
        type_map = {
            "museum": "museum",
            "park": "park",
            "church": "church",
            "architecture": "architecture",
            "college": "college",
            "cinema": "cinema",
            "theatre": "theatre",
            "entertainment": "entertainment",
            "swimming": "swimmingpool",
            "nightclub": "nightclub",
            "boat": "boat",
            "history": "museum",
            "culture": "museum",
            "nature": "park",
            "sports": "swimmingpool",
        }
        for interest in interests:
            mapped = type_map.get(interest.lower())
            if mapped:
                filters["type"] = mapped
                break  # Use first matching interest for type filter

    # Search
    results = retrieval_service.search(
        domain="attraction",
        query=query,
        filters=filters,
        top_k=5,
    )

    return ToolResult(
        tool_name="attraction_search",
        success=True,
        results=results,
        query_used=query,
    )


# Register this tool
register_tool("attraction_search", search_attraction)
