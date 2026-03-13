"""Tests for cooking-mode tools (set_cooking_timer).

CHANGELOG:
- 2026-03-13: Initial creation — TDD red phase (STORY-067)
"""

import pytest

from app.tools.cooking import register_cooking_tools
from app.tools.registry import ToolRegistry


@pytest.fixture
def registry():
    r = ToolRegistry()
    register_cooking_tools(r)
    return r


@pytest.mark.asyncio
async def test_set_cooking_timer_returns_structured_result(registry):
    """set_cooking_timer returns name, duration, and confirmation."""
    result = await registry.execute(
        "set_cooking_timer",
        {"name": "Sauce", "duration_minutes": 15},
    )
    assert result["name"] == "Sauce"
    assert result["duration_minutes"] == 15
    assert result["duration_seconds"] == 900
    assert "created" in result
    assert result["created"] is True


@pytest.mark.asyncio
async def test_set_cooking_timer_defaults_name(registry):
    """When no name given, uses 'Timer'."""
    result = await registry.execute(
        "set_cooking_timer",
        {"duration_minutes": 5},
    )
    assert result["name"] == "Timer"
    assert result["duration_minutes"] == 5


@pytest.mark.asyncio
async def test_set_cooking_timer_fractional_minutes(registry):
    """Fractional minutes are converted to seconds correctly."""
    result = await registry.execute(
        "set_cooking_timer",
        {"name": "Quick blanch", "duration_minutes": 1.5},
    )
    assert result["duration_seconds"] == 90


@pytest.mark.asyncio
async def test_set_cooking_timer_registered_in_definitions(registry):
    """set_cooking_timer appears in tool definitions."""
    defs = registry.get_definitions()
    names = [d["name"] for d in defs]
    assert "set_cooking_timer" in names


@pytest.mark.asyncio
async def test_set_cooking_timer_schema_has_required_fields(registry):
    """Tool schema defines duration_minutes as required."""
    defs = registry.get_definitions()
    timer_def = next(d for d in defs if d["name"] == "set_cooking_timer")
    assert "duration_minutes" in timer_def["input_schema"]["required"]
