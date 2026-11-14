"""
PlanWise AI - Hotel Search Tool

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


def search_hotel(
    location: Optional[str] = None,
    budget: Optional[Any] = None,
    preferences: Optional[List[str]] = None,
    place: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """
    Search for hotels matching the given criteria.

    Args:
        location: Target area/location name
        budget: Price preference (cheap, moderate, expensive) or an amount
        preferences: List of preferences (e.g., parking, wifi, hostel)
        place: Resolved place (name/lat/lon...) when already geocoded
    """
    pref_list = common.as_list(preferences)
    level = common.price_level(budget, pref_list)
    query = " ".join(["hotel", str(location or "").strip(), level or "", *pref_list]).strip()

    mode, live_place = common.resolve_place(location, place)
    if mode == "unknown":
        return common.unknown_location_result("hotel_search", location, query)

    # ── Live data (anywhere in the world) ────────────────────────
    if live_place is not None:
        records = common.live_search("hotel", live_place)
        if records is None:
            return ToolResult(
                tool_name="hotel_search", success=False, results=[],
                error="Live map data is temporarily unavailable.", query_used=query,
            )

        prefs_text = " ".join(pref_list).lower()

        def boost(r: Dict[str, Any]) -> float:
            score = 0.0
            kind = r.get("type", "")
            stars = int(r.get("stars", 0) or 0)
            if level == "cheap" and kind in ("hostel", "guest house", "motel"):
                score += 3
            if level == "expensive" and (stars >= 4 or kind == "resort"):
                score += 3
            if level == "moderate" and stars == 3:
                score += 2
            for word in ("hostel", "resort", "guest house", "apartment"):
                if word in prefs_text and kind == word:
                    score += 4
            if "guesthouse" in prefs_text and kind == "guest house":
                score += 4
            if ("wifi" in prefs_text or "internet" in prefs_text) and r.get("internet"):
                score += 2
            if "parking" in prefs_text and r.get("parking"):
                score += 2
            for n in ("5", "4", "3"):
                if f"{n}-star" in prefs_text or f"{n} star" in prefs_text:
                    score += 4 if stars == int(n) else 0
            return score

        return ToolResult(
            tool_name="hotel_search", success=True,
            results=common.finalize(common.rerank(records, boost)),
            query_used=query,
        )

    # ── Bundled Cambridge dataset ────────────────────────────────
    filters: Dict[str, Any] = {}
    area = common.local_area(location)
    if area:
        filters["area"] = area
    if level:
        filters["pricerange"] = level
    for p in pref_list:
        p_lower = p.lower()
        if "parking" in p_lower:
            filters["parking"] = "yes"
        if "internet" in p_lower or "wifi" in p_lower:
            filters["internet"] = "yes"
        if "guesthouse" in p_lower or "guest house" in p_lower:
            filters["type"] = "guesthouse"

    results = retrieval_service.search(domain="hotel", query=query, filters=filters, top_k=5)
    return ToolResult(
        tool_name="hotel_search", success=True,
        results=[{**r, "source": "multiwoz"} for r in results],
        query_used=query,
    )


# Register this tool
register_tool("hotel_search", search_hotel)
