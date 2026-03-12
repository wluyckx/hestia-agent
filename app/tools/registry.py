"""
Tool registry — register, look up, and execute tools for Claude tool-use.

CHANGELOG:
- 2026-03-12: Add weekday + date to get_current_time response (date-relative fix)
- 2026-02-28: Initial creation — registry + get_current_time (STORY-035)
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Raised when tool execution fails."""


class ToolRegistry:
    """Registry of tools available to the Claude agent.

    Each tool has a name, description, JSON Schema parameters, and an
    async handler function. The registry provides Anthropic-compatible
    tool definitions and handles execution with timeouts.
    """

    def __init__(self, timeout_seconds: float = 5.0):
        self._tools: dict[str, dict[str, Any]] = {}
        self._timeout = timeout_seconds

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable,
    ) -> None:
        """Register a tool.

        Args:
            name: Unique tool name (e.g., "get_energy_realtime").
            description: Human-readable description for Claude.
            parameters: JSON Schema describing the tool's input parameters.
            handler: Async function that executes the tool. Receives
                keyword arguments matching the parameter schema.
                Must return a dict.
        """
        self._tools[name] = {
            "name": name,
            "description": description,
            "input_schema": parameters,
            "handler": handler,
        }

    def get_definitions(self) -> list[dict]:
        """Return Anthropic-compatible tool definitions.

        Returns a list of dicts with name, description, and input_schema
        suitable for passing to client.messages.stream(tools=...).
        """
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in self._tools.values()
        ]

    def get_tool_descriptions(self) -> list[dict]:
        """Return simplified tool descriptions for the system prompt.

        Returns a list of {"name": ..., "description": ...} dicts.
        """
        return [{"name": t["name"], "description": t["description"]} for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> dict:
        """Execute a tool by name with given arguments.

        Args:
            name: The tool name to execute.
            arguments: Dict of arguments matching the tool's parameter schema.

        Returns:
            Tool result as a dict.

        Raises:
            ToolError: If tool is unknown, execution fails, or times out.
        """
        tool = self._tools.get(name)
        if not tool:
            msg = f"Unknown tool: {name}"
            raise ToolError(msg)

        handler = tool["handler"]
        try:
            result = await asyncio.wait_for(
                handler(**arguments),
                timeout=self._timeout,
            )
        except TimeoutError as e:
            msg = f"Tool '{name}' timed out after {self._timeout}s"
            raise ToolError(msg) from e
        except ToolError:
            raise
        except Exception as e:
            msg = f"Tool '{name}' failed: {e}"
            raise ToolError(msg) from e
        else:
            return result


# ---------- Built-in tools ----------


async def _get_current_time() -> dict:
    """Return current UTC time with weekday for date-relative reasoning."""
    now = datetime.now(UTC)
    return {
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "timezone": "UTC",
    }


def create_default_registry(
    timeout_seconds: float = 5.0,
) -> ToolRegistry:
    """Create a registry with built-in tools pre-registered.

    Domain tools (energy, mealie, shopping) are registered by their
    respective modules in later stories.
    """
    registry = ToolRegistry(timeout_seconds=timeout_seconds)
    registry.register(
        name="get_current_time",
        description="Get the current date and time in UTC",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=_get_current_time,
    )
    return registry
