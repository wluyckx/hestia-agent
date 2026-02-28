"""Tests for cross-domain multi-tool scenarios.

Verifies that the tool-use framework supports Claude chaining
multiple tools from different domains in a single conversation turn.

CHANGELOG:
- 2026-02-28: Initial creation — 3 cross-domain scenarios (STORY-041)
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends import BackendData
from tests.conftest import auth_headers

_EMPTY_DATA = BackendData()
_MOCK_FETCH_ALL = "app.routers.chat.fetch_all"


def _text_block(text: str) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    return block


def _tool_use_block(tool_id: str, name: str, input_data: dict) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", id=tool_id, name=name, input=input_data)
    block.model_dump = lambda: {
        "type": "tool_use",
        "id": tool_id,
        "name": name,
        "input": input_data,
    }
    return block


def _claude_response(content: list, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _mock_anthropic_client(responses: list) -> MagicMock:
    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages
    mock_messages.create = AsyncMock(side_effect=responses)
    return mock_client


# ---- Scenario 1: "What should I cook based on what I usually buy?" ----
# Expected chain: get_top_products → search_recipes


@pytest.mark.asyncio
async def test_scenario_cook_by_purchase(initialized_client):
    """Cross-domain: shopping top products → recipe search."""
    # Round 1: Claude calls get_top_products
    tool_a = _tool_use_block(
        "toolu_a",
        "get_top_products",
        {"limit": 5},
    )
    # Round 2: Claude calls search_recipes based on top product
    tool_b = _tool_use_block(
        "toolu_b",
        "search_recipes",
        {"query": "chicken"},
    )
    # Round 3: Claude synthesizes a response
    final_text = (
        "Based on your frequent purchases, you buy chicken often. "
        "Here are some recipes: [Chicken Stir-fry](/meals/chicken-stir-fry)."
    )

    responses = [
        _claude_response([tool_a], stop_reason="tool_use"),
        _claude_response([tool_b], stop_reason="tool_use"),
        _claude_response([_text_block(final_text)]),
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
                "message": "What should I cook based on what I usually buy?",
                "conversation_id": "cross-domain-1",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    assert mock_client.messages.create.call_count == 3

    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
    text_chunk = json.loads(lines[0].removeprefix("data: "))
    assert "chicken" in text_chunk["token"].lower()

    # Verify both tool domains were called
    call_names = []
    for call in mock_client.messages.create.call_args_list[1:]:
        msgs = call[1]["messages"]
        for msg in msgs:
            if msg["role"] == "user" and isinstance(msg["content"], list):
                for item in msg["content"]:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        call_names.append(item["tool_use_id"])
    assert "toolu_a" in call_names
    assert "toolu_b" in call_names


# ---- Scenario 2: "Give me a household summary" ----
# Expected chain: get_energy_realtime + get_spending_summary + get_meal_plan


@pytest.mark.asyncio
async def test_scenario_household_summary(initialized_client):
    """Cross-domain: energy + spending + meal plan in parallel."""
    # Claude calls all 3 tools in one round (parallel tool use)
    tool_energy = _tool_use_block(
        "toolu_energy",
        "get_energy_realtime",
        {},
    )
    tool_spending = _tool_use_block(
        "toolu_spend",
        "get_spending_summary",
        {},
    )
    tool_meals = _tool_use_block(
        "toolu_meals",
        "get_meal_plan",
        {},
    )

    final_text = (
        "Here's your household summary: "
        "Energy at 435W, groceries EUR 452.30 this month, "
        "tonight's dinner is Pasta Bolognese."
    )

    responses = [
        # Round 1: Claude requests 3 tools simultaneously
        _claude_response(
            [tool_energy, tool_spending, tool_meals],
            stop_reason="tool_use",
        ),
        # Round 2: Claude synthesizes
        _claude_response([_text_block(final_text)]),
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
                "message": "Give me a household summary",
                "conversation_id": "cross-domain-2",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    # Only 2 rounds needed (parallel tool call + final)
    assert mock_client.messages.create.call_count == 2

    # Verify all 3 tool results were sent back
    second_call = mock_client.messages.create.call_args_list[1][1]
    last_msg = second_call["messages"][-1]
    tool_results = [
        item
        for item in last_msg["content"]
        if isinstance(item, dict) and item.get("type") == "tool_result"
    ]
    assert len(tool_results) == 3

    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
    text_chunk = json.loads(lines[0].removeprefix("data: "))
    assert "household summary" in text_chunk["token"].lower()


# ---- Scenario 3: "How much did I spend and is my energy bill going up?" ----
# Expected chain: get_spending_summary + get_tariff_comparison


@pytest.mark.asyncio
async def test_scenario_spend_and_tariff(initialized_client):
    """Cross-domain: spending + energy tariff comparison."""
    tool_spend = _tool_use_block(
        "toolu_s",
        "get_spending_summary",
        {},
    )
    tool_tariff = _tool_use_block(
        "toolu_t",
        "get_tariff_comparison",
        {},
    )

    final_text = (
        "You spent EUR 452.30 this month on groceries. "
        "Your energy tariff is competitive — no action needed."
    )

    responses = [
        _claude_response(
            [tool_spend, tool_tariff],
            stop_reason="tool_use",
        ),
        _claude_response([_text_block(final_text)]),
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
                "message": "How much did I spend and is my energy bill going up?",
                "conversation_id": "cross-domain-3",
                "history": [],
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    assert mock_client.messages.create.call_count == 2

    # Verify both tool results returned
    second_call = mock_client.messages.create.call_args_list[1][1]
    last_msg = second_call["messages"][-1]
    tool_ids = [
        item["tool_use_id"]
        for item in last_msg["content"]
        if isinstance(item, dict) and item.get("type") == "tool_result"
    ]
    assert "toolu_s" in tool_ids
    assert "toolu_t" in tool_ids

    lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
    text_chunk = json.loads(lines[0].removeprefix("data: "))
    assert "452.30" in text_chunk["token"]
