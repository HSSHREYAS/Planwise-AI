"""
PlanWise AI - Restaurant Search Tool

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

CUISINES = [
    "indian", "chinese", "italian", "thai", "japanese", "mexican", "british",
    "european", "african", "korean", "turkish", "portuguese", "seafood",
    "french", "spanish", "mediterranean", "lebanese", "vietnamese", "pizza",
    "burger", "sushi", "south indian", "north indian", "american", "greek",
    "coffee", "biryani", "kebab", "noodle", "regional", "asian", "bakery",
]


def search_restaurant(
    location: Optional[str] = None,
    budget: Optional[Any] = None,
    preferences: Optional[List[str]] = None,
    place: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """
    Search for restaurants matching the given criteria.

    Args:
        location: Target area/location name
        budget: Price preference (cheap, moderate, expensive) or an amount
        preferences: Dietary / cuisine preferences (e.g., vegetarian, italian)
        place: Resolved place (name/lat/lon...) when already geocoded
    """
    pref_list = common.as_list(preferences)
    level = common.price_level(budget, pref_list)
    query = " ".join(["restaurant", str(location or "").strip(), level or "", *pref_list]).strip()
    prefs_text = " ".join(pref_list).lower()
    wanted_cuisines = [c for c in CUISINES if c in prefs_text]

    mode, live_place = common.resolve_place(location, place)
    if mode == "unknown":
        return common.unknown_location_result("restaurant_search", location, query)

    # ── Live data (anywhere in the world) ────────────────────────
    if live_place is not None:
        records = common.live_search("restaurant", live_place)
        if records is None:
            return ToolResult(
                tool_name="restaurant_search", success=False, results=[],
                error="Live map data is temporarily unavailable.", query_used=query,
            )

        wants_veg = "vegetarian" in prefs_text or "veg" in prefs_text.split()
        wants_vegan = "vegan" in prefs_text

        def boost(r: Dict[str, Any]) -> float:
            score = 0.0
            food = r.get("food", "").lower()
            kind = r.get("type", "")
            name = r.get("name", "").lower()
            if wants_veg and (r.get("vegetarian") or "veg" in name.split()):
                score += 5
            if wants_vegan and r.get("vegan"):
                score += 5
            for cuisine in wanted_cuisines:
                if cuisine in food or cuisine in name:
                    score += 5
            for word in ("cafe", "pub"):
                if word in prefs_text and kind == word:
                    score += 4
            if level == "cheap" and kind in ("fast food", "cafe", "food court"):
                score += 1.5
            if level == "expensive" and kind == "restaurant":
                score += 1.5
            if kind == "restaurant":
                score += 0.5
            return score

        return ToolResult(
            tool_name="restaurant_search", success=True,
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
    if wanted_cuisines:
        filters["food"] = wanted_cuisines[0]

    results = retrieval_service.search(domain="restaurant", query=query, filters=filters, top_k=5)
    return ToolResult(
        tool_name="restaurant_search", success=True,
        results=[{**r, "source": "multiwoz"} for r in results],
        query_used=query,
    )


# Register this tool
register_tool("restaurant_search", search_restaurant)
