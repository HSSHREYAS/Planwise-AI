"""
PlanWise AI - Transport Search Tool

Cambridge, UK: train timetable records from the bundled MultiWOZ data.
Anywhere else: real transport hubs (railway / metro / bus stations and
airports) near the location from OpenStreetMap. Never fabricates
timetables.
"""

import logging
from typing import Any, Dict, Optional

from app.models.schemas import ToolResult
from app.retrieval.search import retrieval_service
from app.tools import common
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def search_transport(
    location: Optional[str] = None,
    source: Optional[str] = None,
    destination: Optional[str] = None,
    place: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """
    Search for transport options.

    Args:
        location: General area
        source: Origin/departure point
        destination: Destination point
        place: Resolved place (name/lat/lon...) when already geocoded
    """
    query_parts = ["transport"]
    if source:
        query_parts.append(f"from {source}")
    if destination:
        query_parts.append(f"to {destination}")
    if location:
        query_parts.append(str(location))
    query = " ".join(query_parts)

    mode, live_place = common.resolve_place(location, place)
    if mode == "unknown":
        return common.unknown_location_result("transport_search", location, query)

    # ── Live data: transport hubs near the place ─────────────────
    if live_place is not None:
        records = common.live_search("transport", live_place)
        if records is None:
            return ToolResult(
                tool_name="transport_search", success=False, results=[],
                error="Live map data is temporarily unavailable.", query_used=query,
            )

        def boost(r: Dict[str, Any]) -> float:
            # Main-line stations and airports first, then by proximity
            base = {"railway station": 3, "airport": 2.5, "metro station": 1.5, "bus station": 2}
            return base.get(r.get("type", ""), 0) - min(r.get("distance_km", 0), 60) * 0.05

        return ToolResult(
            tool_name="transport_search", success=True,
            results=common.finalize(common.rerank(records, boost)),
            query_used=query,
        )

    # ── Bundled Cambridge train data ─────────────────────────────
    filters: Dict[str, Any] = {}
    if source:
        filters["departure"] = source
    if destination:
        filters["destination"] = destination

    results = retrieval_service.search(domain="transport", query=query, filters=filters, top_k=5)
    return ToolResult(
        tool_name="transport_search", success=True,
        results=[{**r, "source": "multiwoz"} for r in results],
        query_used=query,
    )


# Register this tool
register_tool("transport_search", search_transport)
