"""
Household preference store — remember, recall, and forget preferences.

Preferences are scoped to user_id and persisted in SQLite. Active
preferences are injected into the system prompt so Claude uses them
in every conversation.

CHANGELOG:
- 2026-02-28: Initial creation — CRUD tools + prompt helper (STORY-045)
"""

import logging
import uuid
from datetime import UTC, datetime

import aiosqlite

from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


async def get_user_preferences(db: aiosqlite.Connection, user: str) -> list[dict]:
    """Fetch all active preferences for a user.

    Returns a list of {"key": ..., "value": ...} dicts.
    """
    cursor = await db.execute(
        "SELECT key, value FROM preferences WHERE user_id = ? ORDER BY key",
        (user,),
    )
    rows = await cursor.fetchall()
    return [{"key": row[0], "value": row[1]} for row in rows]


def register_memory_tools(
    registry: ToolRegistry,
    db: aiosqlite.Connection,
    user: str,
) -> None:
    """Register preference CRUD tools scoped to the given user."""

    async def remember_preference(key: str, value: str) -> dict:
        """Store or update a household preference."""
        now = datetime.now(UTC).isoformat()
        pref_id = str(uuid.uuid4())

        # Upsert: delete existing then insert
        await db.execute(
            "DELETE FROM preferences WHERE user_id = ? AND key = ?",
            (user, key),
        )
        await db.execute(
            "INSERT INTO preferences (id, user_id, key, value, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pref_id, user, key, value, now, now),
        )
        await db.commit()

        return {"success": True, "key": key, "value": value}

    async def get_preferences() -> dict:
        """Return all active preferences for this household."""
        prefs = await get_user_preferences(db, user)
        return {"preferences": prefs}

    async def forget_preference(key: str) -> dict:
        """Remove a preference by key."""
        cursor = await db.execute(
            "DELETE FROM preferences WHERE user_id = ? AND key = ?",
            (user, key),
        )
        await db.commit()

        if cursor.rowcount == 0:
            return {
                "success": False,
                "message": f"Preference '{key}' not found",
            }

        return {"success": True, "key": key, "message": f"Forgot '{key}'"}

    registry.register(
        name="remember_preference",
        description=(
            "Store a household preference (e.g., dietary restriction, "
            "budget, preferred store). If the key already exists, the "
            "value is updated."
        ),
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": (
                        "Preference key (e.g., 'diet', 'budget_groceries', "
                        "'preferred_store', 'kids_dislikes')"
                    ),
                },
                "value": {
                    "type": "string",
                    "description": "Preference value (e.g., 'vegetarian', 'EUR 600/month')",
                },
            },
            "required": ["key", "value"],
        },
        handler=remember_preference,
    )

    registry.register(
        name="get_preferences",
        description=(
            "Get all stored household preferences. Use this to check "
            "what the household has told you to remember."
        ),
        parameters={"type": "object", "properties": {}},
        handler=get_preferences,
    )

    registry.register(
        name="forget_preference",
        description=(
            "Remove a stored preference by key. Use when the user says "
            "'forget that I'm vegetarian' or 'remove my budget preference'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The preference key to remove",
                },
            },
            "required": ["key"],
        },
        handler=forget_preference,
    )
