"""
PlanWise AI - Transport Search Tool

Searches local MultiWOZ-derived transport data (train + taxi).
Never fabricates results.
"""

import logging
from typing import List, Optional

from app.models.schemas import ToolResult
from app.retrieval.search import retrieval_service
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def search_transport(
    location: Optional[str] = None,
    source: Optional[str] = None,
    destination: Optional[str] = None,
) -> ToolResult:
    """
    Search for transport options.

    Args:
        location: General area
        source: Origin/departure point
        destination: Destination point

    Returns:
        ToolResult with matching transport records
    """
    # Build search query
    query_parts = ["transport"]
    if source:
        query_parts.append(f"from {source}")
    if destination:
        query_parts.append(f"to {destination}")
    if location:
        query_parts.append(location)
    query = " ".join(query_parts)

    # Build metadata filters
    filters = {}
    if source:
        filters["departure"] = source
    if destination:
        filters["destination"] = destination

    # Search
    results = retrieval_service.search(
        domain="transport",
        query=query,
        filters=filters,
        top_k=5,
    )

    return ToolResult(
        tool_name="transport_search",
        success=True,
        results=results,
        query_used=query,
    )


# Register this tool
register_tool("transport_search", search_transport)
