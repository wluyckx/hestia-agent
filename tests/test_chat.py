"""Tests for the chat SSE streaming endpoint with tool-use.

CHANGELOG:
- 2026-02-28: Refactor mocks for tool-use loop (STORY-035)
- 2026-02-28: Initial creation (STORY-034)
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends import BackendData
from tests.conftest import auth_headers

# All tests mock fetch_all to avoid real HTTP calls to backends
_EMPTY_DATA = BackendData()
_MOCK_FETCH_ALL = "app.routers.chat.fetch_all"


def _text_block(text: str) -> SimpleNamespace:
    """Create a mock text content block."""
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_id: str, name: str, input_data: dict) -> SimpleNamespace:
    """Create a mock tool_use content block."""
    block = SimpleNamespace(type="tool_use", id=tool_id, name=name, input=input_data)
    block.model_dump = lambda: {
        "type": "tool_use",
        "id": tool_id,
        "name": name,
        "input": input_data,
    }
    return block


def _claude_response(content: list, stop_reason: str = "end_turn") -> SimpleNamespace:
    """Create a mock Claude messages.create() response."""
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _mock_anthropic_client(responses: list) -> MagicMock:
    """Create a mock AsyncAnthropic client that returns given responses.

    Each call to client.messages.create() returns the next response.
    """
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.create = AsyncMock(side_effect=responses)
    return mock_client


@pytest.mark.asyncio
async def test_chat_streams_sse_response(initialized_client):
    """Simple text response streams as SSE."""
    responses = [_claude_response([_text_block("Hello world")])]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
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

    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
    assert len(lines) == 2  # text + done

    chunk1 = json.loads(lines[0].removeprefix("data: "))
    assert chunk1["token"] == "Hello world"
    assert chunk1["done"] is False
    assert chunk1["conversation_id"] == "test-conv-1"

    done_chunk = json.loads(lines[-1].removeprefix("data: "))
    assert done_chunk["done"] is True
    assert "message_id" in done_chunk


@pytest.mark.asyncio
async def test_chat_creates_conversation_if_missing(initialized_client):
    responses = [_claude_response([_text_block("Ok")])]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
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

    list_resp = await initialized_client.get("/conversations", headers=auth_headers())
    convos = list_resp.json()["conversations"]
    assert any(c["id"] == "auto-created-conv" for c in convos)


@pytest.mark.asyncio
async def test_chat_persists_messages(initialized_client):
    responses = [_claude_response([_text_block("Reply")])]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
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
    responses = [_claude_response([_text_block("Ok")])]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
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

    call_kwargs = mock_client.messages.create.call_args[1]
    msgs = call_kwargs["messages"]
    assert msgs[0] == {"role": "user", "content": "Hello"}
    assert msgs[1] == {"role": "assistant", "content": "Hi there"}
    assert msgs[2] == {"role": "user", "content": "Follow-up"}


@pytest.mark.asyncio
async def test_chat_system_prompt_includes_backend_data(initialized_client):
    """System prompt should include live data when backends return data."""
    responses = [_claude_response([_text_block("Ok")])]
    mock_client = _mock_anthropic_client(responses)

    live_data = BackendData(
        energy={"power_w": 1500},
        solar={
            "pv_power_w": 3200,
            "battery_soc_pct": 85,
            "pv_daily_kwh": 12.5,
        },
        spending={"total_cents": 45230, "currency": "EUR"},
        meals=[{"recipe": {"name": "Pasta Bolognese"}}],
    )

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=live_data,
        ),
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

    call_kwargs = mock_client.messages.create.call_args[1]
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


# ---- Tool-use tests (STORY-035) ----


@pytest.mark.asyncio
async def test_chat_executes_tool_and_returns_result(initialized_client):
    """Claude calls get_current_time, agent executes it, Claude responds."""
    tool_block = _tool_use_block("toolu_123", "get_current_time", {})
    responses = [
        # Round 1: Claude requests tool use
        _claude_response([tool_block], stop_reason="tool_use"),
        # Round 2: Claude responds with text after receiving tool result
        _claude_response([_text_block("The time is 2026-02-28.")]),
    ]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
    ):
        resp = await initialized_client.post(
            "/chat",
            json={
                "message": "What time is it?",
                "conversation_id": "tool-test",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]

    # Should have text + done
    text_chunk = json.loads(lines[0].removeprefix("data: "))
    assert text_chunk["token"] == "The time is 2026-02-28."
    assert text_chunk["done"] is False

    done_chunk = json.loads(lines[-1].removeprefix("data: "))
    assert done_chunk["done"] is True

    # Verify Claude was called twice (tool round + final)
    assert mock_client.messages.create.call_count == 2

    # Verify second call includes tool result
    second_call = mock_client.messages.create.call_args_list[1][1]
    msgs = second_call["messages"]
    # Last user message should contain tool_result
    last_user_msg = msgs[-1]
    assert last_user_msg["role"] == "user"
    assert any(item.get("type") == "tool_result" for item in last_user_msg["content"])


@pytest.mark.asyncio
async def test_chat_multi_tool_calls(initialized_client):
    """Claude calls two tools in sequence, then responds."""
    # Round 1: Claude calls tool A
    tool_a = _tool_use_block("toolu_a", "get_current_time", {})
    # Round 2: Claude calls tool B (after getting result from A)
    tool_b = _tool_use_block("toolu_b", "get_current_time", {})

    responses = [
        _claude_response([tool_a], stop_reason="tool_use"),
        _claude_response([tool_b], stop_reason="tool_use"),
        _claude_response([_text_block("Both tools done.")]),
    ]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
    ):
        resp = await initialized_client.post(
            "/chat",
            json={
                "message": "Do two things",
                "conversation_id": "multi-tool",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    assert mock_client.messages.create.call_count == 3

    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
    text_chunk = json.loads(lines[0].removeprefix("data: "))
    assert text_chunk["token"] == "Both tools done."


@pytest.mark.asyncio
async def test_chat_tool_error_handled_gracefully(initialized_client):
    """When a tool fails, error is sent to Claude and it responds."""
    tool_block = _tool_use_block("toolu_err", "nonexistent_tool", {})
    responses = [
        _claude_response([tool_block], stop_reason="tool_use"),
        _claude_response([_text_block("Sorry, I couldn't get that data.")]),
    ]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
    ):
        resp = await initialized_client.post(
            "/chat",
            json={
                "message": "Call something broken",
                "conversation_id": "error-tool",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200

    # Verify error was sent as tool_result with is_error=True
    second_call = mock_client.messages.create.call_args_list[1][1]
    last_msg = second_call["messages"][-1]
    tool_results = [item for item in last_msg["content"] if item.get("type") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["is_error"] is True
    assert "Unknown tool" in tool_results[0]["content"]

    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
    text_chunk = json.loads(lines[0].removeprefix("data: "))
    assert "Sorry" in text_chunk["token"]


@pytest.mark.asyncio
async def test_chat_passes_tool_definitions(initialized_client):
    """Verify tool definitions are passed to Claude."""
    responses = [_claude_response([_text_block("Ok")])]
    mock_client = _mock_anthropic_client(responses)

    with (
        patch(
            "app.routers.chat.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
        patch(
            _MOCK_FETCH_ALL,
            new_callable=AsyncMock,
            return_value=_EMPTY_DATA,
        ),
    ):
        await initialized_client.post(
            "/chat",
            json={
                "message": "Hello",
                "conversation_id": "tools-test",
                "history": [],
            },
            headers=auth_headers(),
        )

    call_kwargs = mock_client.messages.create.call_args[1]
    tools = call_kwargs["tools"]
    # At minimum, get_current_time should be registered
    tool_names = [t["name"] for t in tools]
    assert "get_current_time" in tool_names
