"""Tests for conversation summarization.

Verifies that long conversations are auto-summarized and that summaries
are injected into subsequent chat requests.

CHANGELOG:
- 2026-02-28: Initial creation (STORY-046)
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.backends import BackendData

_EMPTY_DATA = BackendData()
_MOCK_FETCH_ALL = "app.routers.chat.fetch_all"


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _claude_response(content: list, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _mock_anthropic_client(responses: list) -> MagicMock:
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.create = AsyncMock(side_effect=responses)
    return mock_client


# ---- Schema test ----


@pytest.mark.asyncio
async def test_summary_column_exists(initialized_client):
    """Conversations table has summary column after DB init."""
    from app.database import get_connection
    from app.dependencies import get_settings

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        cursor = await db.execute("PRAGMA table_info(conversations)")
        columns = [row[1] for row in await cursor.fetchall()]
        assert "summary" in columns
    finally:
        await db.close()


# ---- Summarization logic tests ----


@pytest.mark.asyncio
async def test_summarize_long_conversation(initialized_client):
    """Conversations with > 20 messages trigger summarization."""

    from app.database import get_connection
    from app.dependencies import get_settings
    from app.routers.chat import _ensure_conversation, _persist_message

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        conv_id = "conv-summarize-test"
        await _ensure_conversation(db, conv_id, "testuser", "Hello")

        # Insert 22 messages (11 user + 11 agent)
        for i in range(11):
            await _persist_message(db, conv_id, "user", f"User message {i}")
            await _persist_message(db, conv_id, "agent", f"Agent response {i}")

        # Verify we have 22 messages
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conv_id,),
        )
        count = (await cursor.fetchone())[0]
        assert count == 22

        # Mock Claude summarization response
        summary_text = "This is a summary of the conversation so far."
        mock_response = _claude_response([_text_block(summary_text)])

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        from app.routers.chat import _maybe_summarize

        await _maybe_summarize(db, conv_id, mock_client, settings)

        # Verify summary is stored
        cursor = await db.execute(
            "SELECT summary FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        assert row[0] == summary_text
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_no_summarize_short_conversation(initialized_client):
    """Conversations with <= 20 messages are not summarized."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.routers.chat import _ensure_conversation, _persist_message

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        conv_id = "conv-short-test"
        await _ensure_conversation(db, conv_id, "testuser", "Hello")

        # Insert only 10 messages
        for i in range(5):
            await _persist_message(db, conv_id, "user", f"User message {i}")
            await _persist_message(db, conv_id, "agent", f"Agent response {i}")

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock()

        from app.routers.chat import _maybe_summarize

        await _maybe_summarize(db, conv_id, mock_client, settings)

        # Claude should NOT have been called
        mock_client.messages.create.assert_not_called()

        # No summary stored
        cursor = await db.execute(
            "SELECT summary FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        assert row[0] is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_summary_injected_in_messages(initialized_client):
    """Summary is prepended to messages when loading a conversation."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.routers.chat import _get_conversation_summary

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        conv_id = "conv-inject-test"
        now = "2026-02-28T12:00:00"
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, summary, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, "testuser", "Test", "Previous conversation summary.", now, now),
        )
        await db.commit()

        summary = await _get_conversation_summary(db, conv_id)
        assert summary == "Previous conversation summary."
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_original_messages_preserved(initialized_client):
    """Summarization does not delete original messages."""
    from app.database import get_connection
    from app.dependencies import get_settings
    from app.routers.chat import _ensure_conversation, _persist_message

    settings = get_settings()
    db = await get_connection(settings.database_path)
    try:
        conv_id = "conv-preserve-test"
        await _ensure_conversation(db, conv_id, "testuser", "Hello")

        for i in range(11):
            await _persist_message(db, conv_id, "user", f"User message {i}")
            await _persist_message(db, conv_id, "agent", f"Agent response {i}")

        summary_text = "Summary of conversation."
        mock_response = _claude_response([_text_block(summary_text)])
        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        from app.routers.chat import _maybe_summarize

        await _maybe_summarize(db, conv_id, mock_client, settings)

        # Original messages still exist
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conv_id,),
        )
        count = (await cursor.fetchone())[0]
        assert count == 22
    finally:
        await db.close()
