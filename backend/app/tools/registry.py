"""
PlanWise AI - Tool Registry

Central registry mapping tool names to functions.
Based on Architecture doc Section 9.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from app.models.schemas import ToolResult

logger = logging.getLogger(__name__)


# Registry populated by tool modules on import
TOOL_REGISTRY: Dict[str, Callable] = {}


def register_tool(name: str, func: Callable) -> None:
    """Register a tool function in the central registry."""
    TOOL_REGISTRY[name] = func
    logger.debug(f"Tool registered: {name}")


def execute_tool(
    tool_name: str,
    parameters: Dict[str, Any],
) -> ToolResult:
    """
    Execute a registered tool with validated parameters.

    The LLM requests a tool → Python validates it exists →
    Python executes it → returns structured result.

    Args:
        tool_name: Name of the tool to execute
        parameters: Tool parameters

    Returns:
        ToolResult with success/failure and results
    """
    if tool_name not in TOOL_REGISTRY:
        logger.error(f"Unknown tool requested: {tool_name}")
        return ToolResult(
            tool_name=tool_name,
            success=False,
            results=[],
            error=f"Unknown tool: {tool_name}. "
                   f"Available tools: {list(TOOL_REGISTRY.keys())}",
        )

    tool_func = TOOL_REGISTRY[tool_name]

    try:
        logger.info(f"Executing tool: {tool_name} with params: {parameters}")
        result = tool_func(**parameters)
        logger.info(
            f"Tool {tool_name} returned {len(result.results)} results"
        )
        return result
    except TypeError as e:
        logger.error(f"Tool {tool_name} parameter error: {e}")
        return ToolResult(
            tool_name=tool_name,
            success=False,
            results=[],
            error=f"Invalid parameters for {tool_name}: {e}",
        )
    except Exception as e:
        logger.error(f"Tool {tool_name} execution failed: {e}")
        return ToolResult(
            tool_name=tool_name,
            success=False,
            results=[],
            error=f"Tool execution failed: {e}",
        )


def get_available_tools() -> List[str]:
    """Return list of registered tool names."""
    return list(TOOL_REGISTRY.keys())


def get_tool_descriptions() -> str:
    """Return formatted tool descriptions for LLM prompts."""
    descriptions = {
        "hotel_search": "Search for hotels (params: location, budget, preferences)",
        "restaurant_search": "Search for restaurants (params: location, budget, preferences)",
        "attraction_search": "Search for attractions (params: location, interests)",
        "transport_search": "Search for transport options (params: location, source, destination)",
    }
    parts = []
    for name in TOOL_REGISTRY:
        desc = descriptions.get(name, f"Tool: {name}")
        parts.append(f"- {name}: {desc}")
    return "\n".join(parts)
