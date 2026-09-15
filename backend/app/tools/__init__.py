"""
PlanWise AI - Tools Package

Import all tool modules to populate TOOL_REGISTRY automatically.
"""

from app.tools.registry import TOOL_REGISTRY, execute_tool, get_available_tools, get_tool_descriptions, register_tool
import app.tools.hotel  # noqa: F401
import app.tools.restaurant  # noqa: F401
import app.tools.attraction  # noqa: F401
import app.tools.transport  # noqa: F401

__all__ = [
    "TOOL_REGISTRY",
    "execute_tool",
    "get_available_tools",
    "get_tool_descriptions",
    "register_tool",
]
