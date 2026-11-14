"""
PlanWise AI - Shared tool helpers

Routing between the two data sources:

  * live OpenStreetMap data  → any place in the world
  * bundled MultiWOZ dataset → Cambridge, UK (richer price information)
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.geo import geocoder, places
from app.geo.geocoder import Place
from app.models.schemas import ToolResult

logger = logging.getLogger(__name__)

LOCAL_AREAS = ("centre", "south", "north", "east", "west")
LIVE_TOP_K = 8


def as_list(value: Any) -> List[str]:
    """Normalize a str / list / None parameter to a list of clean strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if v and str(v).strip()]
    return []


def price_level(budget: Any, preferences: Optional[List[str]] = None) -> Optional[str]:
    """Map a budget description (or numeric amount) to cheap/moderate/expensive."""
    texts = [str(budget).lower().strip()] if budget is not None else []
    texts += [p.lower() for p in (preferences or [])]
    for text in texts:
        if any(w in text for w in ("cheap", "budget", "low", "inexpensive", "affordable")):
            return "cheap"
        if any(w in text for w in ("moderate", "medium", "mid", "comfort")):
            return "moderate"
        if any(w in text for w in ("expensive", "luxury", "high", "fine", "premium")):
            return "expensive"
    if budget is not None:
        match = re.search(r"[\d.]+", str(budget))
        if match:
            try:
                value = float(match.group(0))
            except ValueError:
                return None
            if value < 500:
                return "cheap"
            if value <= 1500:
                return "moderate"
            return "expensive"
    return None


def local_area(location: Optional[str]) -> Optional[str]:
    """Cambridge dataset area (centre/north/...) mentioned in a location string."""
    if not location:
        return None
    text = str(location).lower().replace("center", "centre")
    for area in LOCAL_AREAS:
        if re.search(rf"\b{area}\b", text):
            return area
    return None


def strip_area_words(location: str) -> str:
    """'the centre of Cambridge' → 'Cambridge' (for geocoding)."""
    cleaned = re.sub(
        r"\b(the\s+)?(city\s+)?(centre|center|south|north|east|west)(\s+(part|side|area))?(\s+of)?\b",
        " ", location, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned or location


def resolve_place(
    location: Optional[str], place: Optional[Dict[str, Any]]
) -> Tuple[str, Optional[Place]]:
    """
    Decide which data source a tool call should use.

    Returns (mode, place):
        ("local", None)    → bundled Cambridge dataset
        ("live", Place)    → live OpenStreetMap data around the place
        ("unknown", None)  → a location was named but could not be located
    """
    if place:
        try:
            resolved = Place.model_validate(place)
        except Exception:
            resolved = None
        if resolved is not None:
            if geocoder.is_cambridge_uk(resolved):
                return "local", None
            return "live", resolved

    text = (location or "").strip()
    if not text:
        return "local", None
    bare = strip_area_words(text).lower()
    if (
        text.lower().replace("center", "centre") in LOCAL_AREAS
        or bare in LOCAL_AREAS
        or bare in ("cambridge", "cambridge uk", "cambridge, uk", "cambridge england")
    ):
        return "local", None

    resolved = geocoder.geocode(strip_area_words(text))
    if resolved is None:
        return "unknown", None
    if geocoder.is_cambridge_uk(resolved):
        return "local", None
    return "live", resolved


def unknown_location_result(tool_name: str, location: Optional[str], query: str) -> ToolResult:
    return ToolResult(
        tool_name=tool_name, success=False, results=[],
        error=f"Could not find '{location}' on the map.", query_used=query,
    )


def live_search(domain: str, place: Place) -> Optional[List[Dict[str, Any]]]:
    """Ranked live records for one domain (None if the live lookup failed)."""
    return places.fetch_places(place, [domain]).get(domain)


def rerank(records: List[Dict[str, Any]], boost) -> List[Dict[str, Any]]:
    """Stable re-rank: records with a higher boost(record) come first."""
    return sorted(records, key=lambda r: (-(boost(r) or 0), -r.get("_score", 0)))


def finalize(records: List[Dict[str, Any]], top_k: int = LIVE_TOP_K) -> List[Dict[str, Any]]:
    return [places.public_record(r) for r in records[:top_k]]
