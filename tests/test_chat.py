"""Tests for the chat SSE streaming endpoint."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends import BackendData
from tests.conftest import auth_headers

# All tests mock fetch_all to avoid real HTTP calls to backends
_EMPTY_DATA = BackendData()
_MOCK_FETCH_ALL = "app.routers.chat.fetch_all"


class MockTextStream:
    """Mock async iterator for Anthropic text_stream."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


class MockStreamContext:
    """Mock async context manager for client.messages.stream()."""

    def __init__(self, chunks):
        self.text_stream = MockTextStream(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_chat_streams_sse_response(initialized_client):
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.stream = MagicMock(return_value=MockStreamContext(["Hello", " world"]))

    with (
        patch("app.routers.chat.anthropic.AsyncAnthropic", return_value=mock_client),
        patch(_MOCK_FETCH_ALL, new_callable=AsyncMock, return_value=_EMPTY_DATA),
    ):
        resp = await initialized_client.post(
            "/chat",
            json={
                "message": "Hi there",
                "conversation_id": "test-conv-1",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    # Parse SSE lines
    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
    assert len(lines) == 3  # "Hello", " world", done

    chunk1 = json.loads(lines[0].removeprefix("data: "))
    assert chunk1["token"] == "Hello"
    assert chunk1["done"] is False
    assert chunk1["conversation_id"] == "test-conv-1"

    done_chunk = json.loads(lines[-1].removeprefix("data: "))
    assert done_chunk["done"] is True
    assert "message_id" in done_chunk


@pytest.mark.asyncio
async def test_chat_creates_conversation_if_missing(initialized_client):
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.stream = MagicMock(return_value=MockStreamContext(["Ok"]))

    with (
        patch("app.routers.chat.anthropic.AsyncAnthropic", return_value=mock_client),
        patch(_MOCK_FETCH_ALL, new_callable=AsyncMock, return_value=_EMPTY_DATA),
    ):
        resp = await initialized_client.post(
            "/chat",
            json={
                "message": "Create me",
                "conversation_id": "auto-created-conv",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200

    # Verify conversation was created
    list_resp = await initialized_client.get("/conversations", headers=auth_headers())
    convos = list_resp.json()["conversations"]
    assert any(c["id"] == "auto-created-conv" for c in convos)


@pytest.mark.asyncio
async def test_chat_persists_messages(initialized_client):
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.stream = MagicMock(return_value=MockStreamContext(["Reply"]))

    with (
        patch("app.routers.chat.anthropic.AsyncAnthropic", return_value=mock_client),
        patch(_MOCK_FETCH_ALL, new_callable=AsyncMock, return_value=_EMPTY_DATA),
    ):
        await initialized_client.post(
            "/chat",
            json={
                "message": "User msg",
                "conversation_id": "persist-test",
                "history": [],
            },
            headers=auth_headers(),
        )

    msgs_resp = await initialized_client.get(
        "/conversations/persist-test/messages", headers=auth_headers()
    )
    messages = msgs_resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "User msg"
    assert messages[1]["role"] == "agent"
    assert messages[1]["content"] == "Reply"


@pytest.mark.asyncio
async def test_chat_maps_agent_role_to_assistant(initialized_client):
    """PWA sends role 'agent' but Anthropic API expects 'assistant'."""
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.stream = MagicMock(return_value=MockStreamContext(["Ok"]))

    with (
        patch("app.routers.chat.anthropic.AsyncAnthropic", return_value=mock_client),
        patch(_MOCK_FETCH_ALL, new_callable=AsyncMock, return_value=_EMPTY_DATA),
    ):
        await initialized_client.post(
            "/chat",
            json={
                "message": "Follow-up",
                "conversation_id": "role-map-test",
                "history": [
                    {"role": "user", "content": "Hello"},
                    {"role": "agent", "content": "Hi there"},
                ],
            },
            headers=auth_headers(),
        )

    # Verify the messages passed to Anthropic have "assistant" not "agent"
    call_kwargs = mock_messages.stream.call_args[1]
    msgs = call_kwargs["messages"]
    assert msgs[0] == {"role": "user", "content": "Hello"}
    assert msgs[1] == {"role": "assistant", "content": "Hi there"}
    assert msgs[2] == {"role": "user", "content": "Follow-up"}


@pytest.mark.asyncio
async def test_chat_system_prompt_includes_backend_data(initialized_client):
    """System prompt should include live data when backends return data."""
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.stream = MagicMock(return_value=MockStreamContext(["Ok"]))

    live_data = BackendData(
        energy={"power_w": 1500},
        solar={"solar_power_w": 3200, "battery_soc": 85, "daily_solar_kwh": 12.5},
        spending={"total_cents": 45230, "currency": "EUR"},
        meals=[{"recipe": {"name": "Pasta Bolognese"}}],
    )

    with (
        patch("app.routers.chat.anthropic.AsyncAnthropic", return_value=mock_client),
        patch(_MOCK_FETCH_ALL, new_callable=AsyncMock, return_value=live_data),
    ):
        await initialized_client.post(
            "/chat",
            json={
                "message": "What did I spend?",
                "conversation_id": "context-test",
                "history": [],
            },
            headers=auth_headers(),
        )

    call_kwargs = mock_messages.stream.call_args[1]
    system = call_kwargs["system"]
    assert "1500W" in system
    assert "452.30" in system
    assert "Pasta Bolognese" in system
    assert "85%" in system


@pytest.mark.asyncio
async def test_chat_requires_auth(initialized_client):
    resp = await initialized_client.post(
        "/chat",
        json={"message": "Hi", "conversation_id": "x", "history": []},
    )
    assert resp.status_code == 401
