"""Tests for household preference store.

Verifies CRUD operations, system prompt injection, and user isolation
for the preference memory system.

CHANGELOG:
- 2026-02-28: Initial creation (STORY-045)
"""

from unittest.mock import AsyncMock

import pytest

# ---- Database schema tests ----


@pytest.mark.asyncio
async def test_preferences_table_created(initialized_client):
    """Preferences table exists after DB init."""
    from app.database import get_connection
    from app.dependencies import get_settings

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='preferences'"
        )
        row = await cursor.fetchone()
        assert row is not None
    finally:
        await db.close()


# ---- Tool registration tests ----


@pytest.mark.asyncio
async def test_register_memory_tools():
    """Memory tools are registered with correct names."""
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    registry = ToolRegistry()
    db = AsyncMock()
    register_memory_tools(registry, db, user="testuser")

    defs = registry.get_definitions()
    names = {d["name"] for d in defs}
    assert "remember_preference" in names
    assert "get_preferences" in names
    assert "forget_preference" in names
    assert len(defs) == 3


# ---- CRUD operation tests ----


@pytest.mark.asyncio
async def test_remember_preference(initialized_client):
    """remember_preference stores a key-value pair."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        registry = ToolRegistry()
        register_memory_tools(registry, db, user="testuser")

        result = await registry.execute(
            "remember_preference",
            {"key": "diet", "value": "vegetarian"},
        )
        assert result["success"] is True
        assert result["key"] == "diet"

        # Verify in DB
        cursor = await db.execute(
            "SELECT value FROM preferences WHERE user_id = ? AND key = ?",
            ("testuser", "diet"),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "vegetarian"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_remember_preference_updates_existing(initialized_client):
    """remember_preference updates value if key already exists."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        registry = ToolRegistry()
        register_memory_tools(registry, db, user="testuser")

        await registry.execute(
            "remember_preference",
            {"key": "budget", "value": "500"},
        )
        await registry.execute(
            "remember_preference",
            {"key": "budget", "value": "600"},
        )

        result = await registry.execute("get_preferences", {})
        budget = [p for p in result["preferences"] if p["key"] == "budget"]
        assert len(budget) == 1
        assert budget[0]["value"] == "600"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_get_preferences_empty(initialized_client):
    """get_preferences returns empty list when no preferences set."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        registry = ToolRegistry()
        register_memory_tools(registry, db, user="testuser")

        result = await registry.execute("get_preferences", {})
        assert result["preferences"] == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_get_preferences_returns_all(initialized_client):
    """get_preferences returns all stored preferences."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        registry = ToolRegistry()
        register_memory_tools(registry, db, user="testuser")

        await registry.execute(
            "remember_preference",
            {"key": "diet", "value": "vegetarian"},
        )
        await registry.execute(
            "remember_preference",
            {"key": "store", "value": "Colruyt"},
        )

        result = await registry.execute("get_preferences", {})
        keys = {p["key"] for p in result["preferences"]}
        assert "diet" in keys
        assert "store" in keys
        assert len(result["preferences"]) == 2
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_forget_preference(initialized_client):
    """forget_preference removes a preference by key."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        registry = ToolRegistry()
        register_memory_tools(registry, db, user="testuser")

        await registry.execute(
            "remember_preference",
            {"key": "diet", "value": "vegetarian"},
        )
        result = await registry.execute(
            "forget_preference",
            {"key": "diet"},
        )
        assert result["success"] is True

        prefs = await registry.execute("get_preferences", {})
        assert prefs["preferences"] == []
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_forget_preference_nonexistent(initialized_client):
    """forget_preference returns not_found for missing key."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        registry = ToolRegistry()
        register_memory_tools(registry, db, user="testuser")

        result = await registry.execute(
            "forget_preference",
            {"key": "nonexistent"},
        )
        assert result["success"] is False
        assert "not found" in result["message"].lower()
    finally:
        await db.close()


# ---- User isolation tests ----


@pytest.mark.asyncio
async def test_user_isolation(initialized_client):
    """Preferences are scoped to user_id — users can't see each other's prefs."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        # User A stores a preference
        registry_a = ToolRegistry()
        register_memory_tools(registry_a, db, user="user_a")
        await registry_a.execute(
            "remember_preference",
            {"key": "diet", "value": "vegan"},
        )

        # User B stores a different preference
        registry_b = ToolRegistry()
        register_memory_tools(registry_b, db, user="user_b")
        await registry_b.execute(
            "remember_preference",
            {"key": "diet", "value": "keto"},
        )

        # User A only sees their own
        result_a = await registry_a.execute("get_preferences", {})
        assert len(result_a["preferences"]) == 1
        assert result_a["preferences"][0]["value"] == "vegan"

        # User B only sees their own
        result_b = await registry_b.execute("get_preferences", {})
        assert len(result_b["preferences"]) == 1
        assert result_b["preferences"][0]["value"] == "keto"
    finally:
        await db.close()


# ---- System prompt injection test ----


@pytest.mark.asyncio
async def test_preferences_in_system_prompt(initialized_client):
    """Preferences are injected into the system prompt."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.tools.memory import get_user_preferences, register_memory_tools
    from app.tools.registry import ToolRegistry

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        registry = ToolRegistry()
        register_memory_tools(registry, db, user="testuser")

        await registry.execute(
            "remember_preference",
            {"key": "diet", "value": "vegetarian"},
        )
        await registry.execute(
            "remember_preference",
            {"key": "budget_groceries", "value": "EUR 600/month"},
        )

        prefs = await get_user_preferences(db, "testuser")
        assert len(prefs) == 2

        # Verify prompt builder includes preferences
        from app.backends import BackendData
        from app.prompts import build_system_prompt

        prompt = build_system_prompt(
            BackendData(),
            tool_descriptions=[],
            preferences=prefs,
        )
        assert "vegetarian" in prompt
        assert "EUR 600/month" in prompt
        assert "household preferences" in prompt.lower() or "preferences" in prompt.lower()
    finally:
        await db.close()
