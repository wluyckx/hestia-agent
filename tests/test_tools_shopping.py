"""Tests for shopping analytics tool handlers.

CHANGELOG:
- 2026-02-28: Initial creation — shopping tool tests (STORY-038)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.tools.registry import ToolRegistry
from app.tools.shopping import (
    _get_product_price_history,
    _get_smart_shopping_list,
    _get_spending_summary,
    _get_top_products,
    register_shopping_tools,
)


def _settings(**overrides) -> Settings:
    """Create a Settings instance with test defaults."""
    defaults = {
        "jwt_secret": "test",
        "shopping_base_url": "http://shopping:8080",
        "shopping_api_key": "key-shop",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_response(json_data, status_code=200):
    """Create a mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ---------- get_spending_summary ----------


@pytest.mark.asyncio
async def test_get_spending_summary_success():
    """Mock spending response, verify correct structure."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "total_cents": 45230,
            "currency": "EUR",
            "month": "2026-02",
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_spending_summary(_settings())

    assert result["total_cents"] == 45230
    assert result["currency"] == "EUR"
    assert result["store"] is None
    assert result["month"] == "2026-02"
    assert "error" not in result


@pytest.mark.asyncio
async def test_get_spending_summary_with_store():
    """Verify store param is passed to API call."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "total_cents": 12000,
            "currency": "EUR",
            "month": "2026-02",
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_spending_summary(_settings(), store="Colruyt")

    assert result["total_cents"] == 12000
    assert result["store"] == "Colruyt"

    # Verify the API was called with the store parameter
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["store"] == "Colruyt"
    assert call_kwargs.kwargs["params"]["months"] == 1


@pytest.mark.asyncio
async def test_get_spending_summary_no_api_key():
    """When shopping_api_key is empty, return error without calling API."""
    result = await _get_spending_summary(_settings(shopping_api_key=""))
    assert result == {"error": "Spending data unavailable"}


# ---------- get_top_products ----------


@pytest.mark.asyncio
async def test_get_top_products_success():
    """Mock products response, verify correct structure."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "products": [
                {"name": "Milk", "count": 15, "last_price_cents": 159},
                {"name": "Bread", "count": 12, "last_price_cents": 249},
            ]
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_top_products(_settings(), limit=5)

    assert len(result["products"]) == 2
    assert result["products"][0]["name"] == "Milk"
    assert result["products"][0]["count"] == 15
    assert result["products"][0]["last_price_cents"] == 159
    assert result["products"][1]["name"] == "Bread"
    assert "error" not in result


# ---------- get_product_price_history ----------


@pytest.mark.asyncio
async def test_get_product_price_history_success():
    """Mock price history response, verify correct structure."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "history": [
                {"date": "2026-02-01", "price_cents": 159, "store": "Colruyt"},
                {"date": "2026-01-15", "price_cents": 149, "store": "Delhaize"},
            ]
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_product_price_history(_settings(), product_name="Milk")

    assert result["product"] == "Milk"
    assert len(result["history"]) == 2
    assert result["history"][0]["date"] == "2026-02-01"
    assert result["history"][0]["price_cents"] == 159
    assert result["history"][0]["store"] == "Colruyt"
    assert result["history"][1]["store"] == "Delhaize"
    assert "error" not in result


# ---------- get_smart_shopping_list ----------


@pytest.mark.asyncio
async def test_get_smart_shopping_list_success():
    """Mock smart list response, verify correct structure."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "items": [
                {
                    "name": "Milk",
                    "urgency": "high",
                    "last_purchased": "2026-02-20",
                    "avg_interval_days": 7,
                },
                {
                    "name": "Eggs",
                    "urgency": "medium",
                    "last_purchased": "2026-02-15",
                    "avg_interval_days": 14,
                },
            ]
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_smart_shopping_list(_settings())

    assert len(result["items"]) == 2
    assert result["items"][0]["name"] == "Milk"
    assert result["items"][0]["urgency"] == "high"
    assert result["items"][0]["last_purchased"] == "2026-02-20"
    assert result["items"][0]["avg_interval_days"] == 7
    assert result["items"][1]["name"] == "Eggs"
    assert "error" not in result


# ---------- register_shopping_tools ----------


def test_register_shopping_tools():
    """Verify all 4 tools appear in registry definitions."""
    registry = ToolRegistry()
    register_shopping_tools(registry, _settings())

    defs = registry.get_definitions()
    tool_names = {d["name"] for d in defs}
    assert "get_spending_summary" in tool_names
    assert "get_top_products" in tool_names
    assert "get_product_price_history" in tool_names
    assert "get_smart_shopping_list" in tool_names
    assert len(defs) == 4
