"""
PlanWise AI - Attraction Search Tool

Live OpenStreetMap data for any location; bundled MultiWOZ data for
Cambridge, UK. Never fabricates results.
"""

import logging
from typing import Any, Dict, List, Optional

from app.models.schemas import ToolResult
from app.retrieval.search import retrieval_service
from app.tools import common
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)

# Interest → MultiWOZ attraction type (bundled dataset)
LOCAL_TYPE_MAP = {
    "museum": "museum", "park": "park", "church": "church",
    "architecture": "architecture", "college": "college", "cinema": "cinema",
    "theatre": "theatre", "entertainment": "entertainment",
    "swimming": "swimmingpool", "nightclub": "nightclub", "boat": "boat",
    "history": "museum", "culture": "museum", "nature": "park",
    "sports": "swimmingpool",
}

# Interest → keywords matched against live record type / name
LIVE_KEYWORDS = {
    "history": ["castle", "fort", "palace", "monument", "ruins", "museum", "memorial", "archaeological", "heritage"],
    "historic": ["castle", "fort", "palace", "monument", "ruins", "museum", "memorial", "archaeological"],
    "culture": ["museum", "gallery", "temple", "palace", "theatre", "arts"],
    "art": ["gallery", "museum", "arts"],
    "nature": ["park", "garden", "viewpoint", "nature reserve", "zoo", "lake"],
    "religious": ["temple", "church", "mosque", "gurdwara", "place of worship", "monastery"],
    "spiritual": ["temple", "church", "mosque", "gurdwara", "place of worship", "monastery"],
    "family": ["zoo", "theme park", "aquarium", "park", "museum"],
    "kids": ["zoo", "theme park", "aquarium", "park"],
    "architecture": ["palace", "castle", "fort", "church", "temple", "monument"],
    "free": [],
}


def search_attraction(
    location: Optional[str] = None,
    interests: Optional[List[str]] = None,
    place: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """
    Search for attractions matching the given criteria.

    Args:
        location: Target area/location name
        interests: Interest categories (e.g., museum, park, history)
        place: Resolved place (name/lat/lon...) when already geocoded
    """
    interest_list = common.as_list(interests)
    query = " ".join(["attraction", str(location or "").strip(), *interest_list]).strip()

    mode, live_place = common.resolve_place(location, place)
    if mode == "unknown":
        return common.unknown_location_result("attraction_search", location, query)

    # ── Live data (anywhere in the world) ────────────────────────
    if live_place is not None:
        records = common.live_search("attraction", live_place)
        if records is None:
            return ToolResult(
                tool_name="attraction_search", success=False, results=[],
                error="Live map data is temporarily unavailable.", query_used=query,
            )

        keywords: List[str] = []
        for interest in interest_list:
            key = interest.lower().rstrip("s")
            keywords.extend(LIVE_KEYWORDS.get(interest.lower(), LIVE_KEYWORDS.get(key, [key])))
        wants_free = any("free" in i.lower() for i in interest_list)

        def boost(r: Dict[str, Any]) -> float:
            score = 0.0
            haystack = f"{r.get('type', '')} {r.get('name', '')}".lower()
            if any(k and k in haystack for k in keywords):
                score += 5
            if wants_free and r.get("entrance_fee") == "free":
                score += 4
            return score

        return ToolResult(
            tool_name="attraction_search", success=True,
            results=common.finalize(common.rerank(records, boost), top_k=10),
            query_used=query,
        )

    # ── Bundled Cambridge dataset ────────────────────────────────
    filters: Dict[str, Any] = {}
    area = common.local_area(location)
    if area:
        filters["area"] = area
    for interest in interest_list:
        mapped = LOCAL_TYPE_MAP.get(interest.lower()) or LOCAL_TYPE_MAP.get(interest.lower().rstrip("s"))
        if mapped:
            filters["type"] = mapped
            break  # first matching interest decides the type filter

    results = retrieval_service.search(domain="attraction", query=query, filters=filters, top_k=6)
    return ToolResult(
        tool_name="attraction_search", success=True,
        results=[{**r, "source": "multiwoz"} for r in results],
        query_used=query,
    )


# Register this tool
register_tool("attraction_search", search_attraction)
