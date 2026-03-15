"""Tests for shopping analytics tool handlers.

CHANGELOG:
- 2026-03-12: Rewrite tests for actual ShoppingReceipts API endpoints
- 2026-02-28: Initial creation — shopping tool tests (STORY-038)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.tools.registry import ToolRegistry
from app.tools.shopping import (
    _get_recent_products,
    _get_smart_shopping_list,
    _get_spending_summary,
    _get_top_products,
    _search_products,
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
    """Mock spending response — matches /v1/analytics/spending/monthly."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "total_cents": 45230,
            "xtra_savings_cents": 1200,
            "net_total_cents": 44030,
            "currency": "EUR",
            "period": "monthly",
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_spending_summary(_settings())

    assert result["total_cents"] == 45230
    assert result["xtra_savings_cents"] == 1200
    assert result["net_total_cents"] == 44030
    assert result["currency"] == "EUR"
    assert "error" not in result


@pytest.mark.asyncio
async def test_get_spending_summary_weekly():
    """Verify weekly period hits the weekly endpoint."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "total_cents": 12000,
            "xtra_savings_cents": 0,
            "net_total_cents": 12000,
            "currency": "EUR",
            "period": "weekly",
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_spending_summary(_settings(), period="weekly")

    assert result["period"] == "weekly"
    call_url = mock_client.get.call_args.args[0]
    assert "spending/weekly" in call_url


@pytest.mark.asyncio
async def test_get_spending_summary_no_api_key():
    """When shopping_api_key is empty, return error without calling API."""
    result = await _get_spending_summary(_settings(shopping_api_key=""))
    assert "error" in result


# ---------- get_top_products ----------


@pytest.mark.asyncio
async def test_get_top_products_success():
    """Mock response matching /v1/analytics/top-products."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        [
            {
                "article_nr": "123",
                "product_name": "Halfvolle Melk",
                "google_category": "dairy",
                "total_spent_cents": 4500,
                "purchase_count": 15,
                "avg_unit_price_cents": 159,
                "first_purchase": "2025-06-01T10:00:00",
                "last_purchase": "2026-03-10T14:00:00",
            },
        ]
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_top_products(_settings(), limit=5)

    assert len(result["products"]) == 1
    assert result["products"][0]["name"] == "Halfvolle Melk"
    assert result["products"][0]["purchase_count"] == 15
    assert result["products"][0]["last_purchase"] == "2026-03-10T14:00:00"
    # Verify correct endpoint
    call_url = mock_client.get.call_args.args[0]
    assert "/v1/analytics/top-products" in call_url


# ---------- search_products ----------


@pytest.mark.asyncio
async def test_search_products_success():
    """Mock response matching /v1/product-concepts/search."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        [
            {
                "product_name": "BONI champignon extra fijn 500g",
                "article_nr": "12345",
                "concept_name": "Champignons",
                "category_path": "Food > Vegetables > Mushrooms",
                "purchase_count": 5,
                "first_purchase": "2025-09-01T00:00:00",
                "last_purchase": "2026-03-05T00:00:00",
            },
        ]
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _search_products(_settings(), query="champignons")

    assert len(result["products"]) == 1
    assert result["products"][0]["name"] == "BONI champignon extra fijn 500g"
    assert result["products"][0]["concept"] == "Champignons"
    assert result["products"][0]["last_purchase"] == "2026-03-05T00:00:00"
    call_url = mock_client.get.call_args.args[0]
    assert "/v1/product-concepts/search" in call_url


@pytest.mark.asyncio
async def test_search_products_no_key():
    """No API key → error dict without calling API."""
    result = await _search_products(_settings(shopping_api_key=""), query="milk")
    assert "error" in result


# ---------- get_recent_products ----------


@pytest.mark.asyncio
async def test_get_recent_products_success():
    """Mock response matching /v1/product-concepts/recent."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        [
            {
                "category_id": 1008316,
                "concept_name": "Bananen",
                "category_path": "Food > Fruits > Bananas",
                "purchase_count": 3,
                "last_purchased": "2026-03-11T15:00:00",
                "top_product_names": ["CHIQUITA banaan", "BONI bananen"],
            },
        ]
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_recent_products(_settings(), days=5)

    assert len(result["products"]) == 1
    assert result["products"][0]["concept"] == "Bananen"
    assert result["products"][0]["last_purchased"] == "2026-03-11T15:00:00"
    assert len(result["products"][0]["examples"]) == 2
    call_url = mock_client.get.call_args.args[0]
    assert "/v1/product-concepts/recent" in call_url


# ---------- get_smart_shopping_list ----------


@pytest.mark.asyncio
async def test_get_smart_shopping_list_success():
    """Mock response matching /v1/smart-list/."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "generated_at": "2026-03-12T18:00:00",
            "language": "nl",
            "total_items": 3,
            "total_estimated_cost_cents": 5000,
            "urgent_items": [
                {
                    "category_id": 100,
                    "concept_name": "Melk",
                    "category_path": "Food > Beverages > Milk",
                    "urgency_level": "urgent",
                    "purchase_reason": "Overdue by 6 days",
                    "priority_score": 1.0,
                    "last_purchase_date": "2026-03-06",
                    "avg_purchase_interval_days": 7,
                    "days_since_last_purchase": 13,
                    "total_purchases": 30,
                    "avg_unit_price_cents": 159,
                    "estimated_cost_cents": 159,
                    "top_product_names": ["BONI volle melk PET 1L"],
                },
            ],
            "high_priority": [
                {
                    "category_id": 200,
                    "concept_name": "Eieren",
                    "category_path": "Food > Eggs",
                    "urgency_level": "high",
                    "purchase_reason": "Due 3 days ago",
                    "priority_score": 0.85,
                    "last_purchase_date": "2026-03-01",
                    "avg_purchase_interval_days": 14,
                    "days_since_last_purchase": 11,
                    "total_purchases": 50,
                    "avg_unit_price_cents": 349,
                    "estimated_cost_cents": 349,
                    "top_product_names": ["BONI scharrelei M 12st"],
                },
            ],
            "medium_priority": [],
        }
    )

    with patch("app.tools.shopping.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_smart_shopping_list(_settings())

    assert result["total_items"] == 3
    assert len(result["urgent"]) == 1
    assert result["urgent"][0]["name"] == "Melk"
    assert result["urgent"][0]["urgency"] == "urgent"
    assert result["urgent"][0]["examples"] == ["BONI volle melk PET 1L"]
    assert len(result["high_priority"]) == 1
    assert result["high_priority"][0]["name"] == "Eieren"
    call_url = mock_client.get.call_args.args[0]
    assert "/v1/smart-list/" in call_url


# ---------- register_shopping_tools ----------


def test_register_shopping_tools():
    """Verify all 5 tools appear in registry definitions."""
    registry = ToolRegistry()
    register_shopping_tools(registry, _settings())

    defs = registry.get_definitions()
    tool_names = {d["name"] for d in defs}
    assert "get_spending_summary" in tool_names
    assert "get_top_products" in tool_names
    assert "search_products" in tool_names
    assert "get_recent_products" in tool_names
    assert "get_smart_shopping_list" in tool_names
    assert len(defs) == 5

    # Verify search_products has required query param
    search_def = next(d for d in defs if d["name"] == "search_products")
    assert "query" in search_def["input_schema"]["required"]
