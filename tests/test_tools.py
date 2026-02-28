"""Tests for the tool-use registry and framework.

CHANGELOG:
- 2026-02-28: Initial creation — tool registry + execution (STORY-035)
"""

import asyncio

import pytest

from app.tools.registry import ToolError, ToolRegistry


class TestToolRegistry:
    """Verify tool registration and lookup."""

    def test_register_and_get_definitions(self):
        registry = ToolRegistry()

        async def dummy_tool(x: str) -> dict:
            return {"result": x}

        registry.register(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "string", "description": "input"}},
                "required": ["x"],
            },
            handler=dummy_tool,
        )

        defs = registry.get_definitions()
        assert len(defs) == 1
        assert defs[0]["name"] == "test_tool"
        assert defs[0]["description"] == "A test tool"
        assert defs[0]["input_schema"]["properties"]["x"]["type"] == "string"

    def test_get_tool_descriptions(self):
        registry = ToolRegistry()

        async def dummy_tool() -> dict:
            return {}

        registry.register(
            name="my_tool",
            description="Does something useful",
            parameters={"type": "object", "properties": {}},
            handler=dummy_tool,
        )

        descriptions = registry.get_tool_descriptions()
        assert len(descriptions) == 1
        assert descriptions[0]["name"] == "my_tool"
        assert descriptions[0]["description"] == "Does something useful"

    def test_empty_registry(self):
        registry = ToolRegistry()
        assert registry.get_definitions() == []
        assert registry.get_tool_descriptions() == []


class TestToolExecution:
    """Verify tool execution, errors, and timeouts."""

    @pytest.mark.asyncio
    async def test_execute_registered_tool(self):
        registry = ToolRegistry()

        async def add_tool(a: int, b: int) -> dict:
            return {"sum": a + b}

        registry.register(
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            handler=add_tool,
        )

        result = await registry.execute("add", {"a": 3, "b": 4})
        assert result == {"sum": 7}

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_raises(self):
        registry = ToolRegistry()
        with pytest.raises(ToolError, match="Unknown tool"):
            await registry.execute("nonexistent", {})

    @pytest.mark.asyncio
    async def test_execute_tool_failure_raises_tool_error(self):
        registry = ToolRegistry()

        async def failing_tool() -> dict:
            msg = "Connection refused"
            raise ConnectionError(msg)

        registry.register(
            name="fail_tool",
            description="Will fail",
            parameters={"type": "object", "properties": {}},
            handler=failing_tool,
        )

        with pytest.raises(ToolError, match="Connection refused"):
            await registry.execute("fail_tool", {})

    @pytest.mark.asyncio
    async def test_execute_tool_timeout(self):
        registry = ToolRegistry(timeout_seconds=0.1)

        async def slow_tool() -> dict:
            await asyncio.sleep(5)
            return {"done": True}

        registry.register(
            name="slow_tool",
            description="Takes forever",
            parameters={"type": "object", "properties": {}},
            handler=slow_tool,
        )

        with pytest.raises(ToolError, match="timed out"):
            await registry.execute("slow_tool", {})


class TestBuiltinGetCurrentTime:
    """Verify the built-in test tool works."""

    @pytest.mark.asyncio
    async def test_get_current_time_returns_iso(self):
        from app.tools.registry import create_default_registry

        registry = create_default_registry()
        result = await registry.execute("get_current_time", {})
        assert "iso" in result
        assert "timezone" in result
        assert result["timezone"] == "UTC"
