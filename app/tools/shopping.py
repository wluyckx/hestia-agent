"""
Shopping analytics tools — spending, products, price history, smart list.

Registers four read-only tools with the ToolRegistry for Claude tool-use:
  - get_spending_summary: monthly grocery spending, optional store filter
  - get_top_products: most frequently purchased products
  - get_product_price_history: price history for a named product
  - get_smart_shopping_list: AI-enhanced shopping suggestions

CHANGELOG:
- 2026-02-28: Initial creation — four shopping read tools (STORY-038)
"""

import logging

import httpx

from app.config import Settings
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


def _headers(settings: Settings) -> dict[str, str]:
    """Build X-API-Key headers for Shopping API calls."""
    return {"X-API-Key": settings.shopping_api_key}


async def _get_spending_summary(settings: Settings, *, store: str | None = None) -> dict:
    """Get monthly grocery spending summary, optionally filtered by store."""
    if not settings.shopping_api_key:
        return {"error": "Spending data unavailable"}
    try:
        params: dict = {"months": 1}
        if store:
            params["store"] = store
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/analytics/spending/monthly",
                params=params,
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "total_cents": data.get("total_cents", 0),
                "currency": data.get("currency", "EUR"),
                "store": store,
                "month": data.get("month", ""),
            }
    except Exception:
        logger.warning("Failed to fetch spending summary", exc_info=True)
        return {"error": "Spending data unavailable"}


async def _get_top_products(settings: Settings, *, limit: int = 10) -> dict:
    """Get the most frequently purchased products."""
    if not settings.shopping_api_key:
        return {"error": "Product data unavailable"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/analytics/products/top",
                params={"limit": limit},
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "products": [
                    {
                        "name": p.get("name", ""),
                        "count": p.get("count", 0),
                        "last_price_cents": p.get("last_price_cents", 0),
                    }
                    for p in data.get("products", [])
                ]
            }
    except Exception:
        logger.warning("Failed to fetch top products", exc_info=True)
        return {"error": "Product data unavailable"}


async def _get_product_price_history(settings: Settings, *, product_name: str) -> dict:
    """Get price history for a specific product."""
    if not settings.shopping_api_key:
        return {"error": "Price history unavailable"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/analytics/products/price-history",
                params={"name": product_name},
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "product": product_name,
                "history": [
                    {
                        "date": h.get("date", ""),
                        "price_cents": h.get("price_cents", 0),
                        "store": h.get("store", ""),
                    }
                    for h in data.get("history", [])
                ],
            }
    except Exception:
        logger.warning("Failed to fetch price history", exc_info=True)
        return {"error": "Price history unavailable"}


async def _get_smart_shopping_list(settings: Settings) -> dict:
    """Get AI-enhanced shopping suggestions based on purchase patterns."""
    if not settings.shopping_api_key:
        return {"error": "Smart list unavailable"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/analytics/smart-list",
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "items": [
                    {
                        "name": item.get("name", ""),
                        "urgency": item.get("urgency", ""),
                        "last_purchased": item.get("last_purchased", ""),
                        "avg_interval_days": item.get("avg_interval_days", 0),
                    }
                    for item in data.get("items", [])
                ]
            }
    except Exception:
        logger.warning("Failed to fetch smart shopping list", exc_info=True)
        return {"error": "Smart list unavailable"}


def register_shopping_tools(registry: ToolRegistry, settings: Settings) -> None:
    """Register all shopping analytics tools with the given registry."""
    registry.register(
        name="get_spending_summary",
        description=("Get monthly grocery spending summary, optionally filtered by store"),
        parameters={
            "type": "object",
            "properties": {
                "store": {
                    "type": "string",
                    "description": "Optional store name filter (e.g., 'Colruyt')",
                },
            },
        },
        handler=lambda **kwargs: _get_spending_summary(settings, **kwargs),
    )

    registry.register(
        name="get_top_products",
        description="Get the most frequently purchased products",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of products to return (default 10)",
                },
            },
        },
        handler=lambda **kwargs: _get_top_products(settings, **kwargs),
    )

    registry.register(
        name="get_product_price_history",
        description="Get price history for a specific product",
        parameters={
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Product name to look up",
                },
            },
            "required": ["product_name"],
        },
        handler=lambda **kwargs: _get_product_price_history(settings, **kwargs),
    )

    registry.register(
        name="get_smart_shopping_list",
        description=(
            "Get AI-enhanced shopping suggestions based on purchase patterns with urgency levels"
        ),
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=lambda **kwargs: _get_smart_shopping_list(settings),
    )
