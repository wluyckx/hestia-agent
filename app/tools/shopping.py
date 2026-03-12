"""
Shopping analytics tools — spending, products, search, smart list.

Registers five read-only tools with the ToolRegistry for Claude tool-use:
  - get_spending_summary: monthly grocery spending
  - get_top_products: most frequently purchased products
  - search_products: search products by name (with last purchase date)
  - get_smart_shopping_list: urgency-based shopping suggestions
  - get_recent_products: recently purchased products

CHANGELOG:
- 2026-03-12: Rewrite tools to match actual ShoppingReceipts API endpoints
- 2026-02-28: Initial creation — four shopping read tools (STORY-038)
"""

import logging

import httpx

from app.config import Settings
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _headers(settings: Settings) -> dict[str, str]:
    """Build X-API-Key headers for Shopping API calls."""
    return {"X-API-Key": settings.shopping_api_key}


def _check_key(settings: Settings) -> dict | None:
    """Return error dict if API key is missing, else None."""
    if not settings.shopping_api_key:
        return {"error": "Shopping API key not configured"}
    return None


async def _get_spending_summary(settings: Settings, *, period: str = "monthly") -> dict:
    """Get grocery spending summary (weekly or monthly)."""
    if err := _check_key(settings):
        return err
    try:
        endpoint = "weekly" if period == "weekly" else "monthly"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/analytics/spending/{endpoint}",
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "total_cents": data.get("total_cents", 0),
                "xtra_savings_cents": data.get("xtra_savings_cents", 0),
                "net_total_cents": data.get("net_total_cents", 0),
                "currency": data.get("currency", "EUR"),
                "period": data.get("period", endpoint),
            }
    except Exception:
        logger.warning("Failed to fetch spending summary", exc_info=True)
        return {"error": "Spending data unavailable"}


async def _get_top_products(settings: Settings, *, limit: int = 10) -> dict:
    """Get the most frequently purchased products."""
    if err := _check_key(settings):
        return err
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/analytics/top-products",
                params={"limit": limit},
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "products": [
                    {
                        "article_nr": p.get("article_nr", ""),
                        "name": p.get("product_name", ""),
                        "category": p.get("google_category", ""),
                        "total_spent_cents": p.get("total_spent_cents", 0),
                        "purchase_count": p.get("purchase_count", 0),
                        "avg_unit_price_cents": p.get("avg_unit_price_cents", 0),
                        "first_purchase": p.get("first_purchase", ""),
                        "last_purchase": p.get("last_purchase", ""),
                    }
                    for p in data
                ]
            }
    except Exception:
        logger.warning("Failed to fetch top products", exc_info=True)
        return {"error": "Product data unavailable"}


async def _search_products(settings: Settings, *, query: str, limit: int = 10) -> dict:
    """Search generic products by name — returns purchase history dates."""
    if err := _check_key(settings):
        return err
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/generic-products/search",
                params={"q": query, "limit": limit},
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            products = data if isinstance(data, list) else data.get("products", [])
            return {
                "products": [
                    {
                        "id": p.get("generic_product_id", ""),
                        "name": p.get("generic_product_name", ""),
                        "name_nl": p.get("name_nl", ""),
                        "category": p.get("google_category", ""),
                        "purchase_count": p.get("retail_product_count", 0),
                        "first_purchase": p.get("first_purchase", ""),
                        "last_purchase": p.get("last_purchase", ""),
                    }
                    for p in products
                ]
            }
    except Exception:
        logger.warning("Failed to search products", exc_info=True)
        return {"error": "Product search unavailable"}


async def _get_recent_products(settings: Settings, *, days: int = 7, limit: int = 20) -> dict:
    """Get recently purchased generic products."""
    if err := _check_key(settings):
        return err
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/generic-products/recent",
                params={"days": days, "limit": limit, "language": "nl"},
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            products = data if isinstance(data, list) else data.get("products", [])
            return {
                "products": [
                    {
                        "id": p.get("generic_product_id", ""),
                        "name": p.get("generic_product_name", ""),
                        "name_nl": p.get("name_nl", ""),
                        "category": p.get("google_category", ""),
                        "purchase_count": p.get("purchase_count", 0),
                        "last_purchased": p.get("last_purchased_at", ""),
                    }
                    for p in products
                ]
            }
    except Exception:
        logger.warning("Failed to fetch recent products", exc_info=True)
        return {"error": "Recent products unavailable"}


async def _get_smart_shopping_list(settings: Settings, *, language: str = "nl") -> dict:
    """Get urgency-based smart shopping suggestions."""
    if err := _check_key(settings):
        return err
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/generic-smart-list/",
                params={"language": language},
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()

            def _extract_items(items: list) -> list[dict]:
                return [
                    {
                        "name": item.get("generic_product_name", ""),
                        "name_nl": item.get("name_nl", ""),
                        "urgency": item.get("urgency_level", ""),
                        "reason": item.get("purchase_reason", ""),
                        "last_purchased": item.get("last_purchase_date", ""),
                        "avg_interval_days": item.get("avg_purchase_interval_days", 0),
                        "days_since_last": item.get("days_since_last_purchase", 0),
                        "estimated_cost_cents": item.get("estimated_cost_cents", 0),
                    }
                    for item in items
                ]

            return {
                "generated_at": data.get("generated_at", ""),
                "total_items": data.get("total_items", 0),
                "total_estimated_cost_cents": data.get("total_estimated_cost_cents", 0),
                "urgent": _extract_items(data.get("urgent_items", [])),
                "high_priority": _extract_items(data.get("high_priority", [])),
                "medium_priority": _extract_items(data.get("medium_priority", [])),
            }
    except Exception:
        logger.warning("Failed to fetch smart shopping list", exc_info=True)
        return {"error": "Smart list unavailable"}


def register_shopping_tools(registry: ToolRegistry, settings: Settings) -> None:
    """Register all shopping analytics tools with the given registry."""
    registry.register(
        name="get_spending_summary",
        description="Get grocery spending summary (weekly or monthly totals with savings)",
        parameters={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Period: 'weekly' or 'monthly' (default: monthly)",
                },
            },
        },
        handler=lambda **kwargs: _get_spending_summary(settings, **kwargs),
    )

    registry.register(
        name="get_top_products",
        description=(
            "Get most frequently purchased products with spend totals and purchase dates"
        ),
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
        name="search_products",
        description=(
            "Search purchased products by name. Returns matching products with "
            "first and last purchase dates — use this to answer 'when did I last buy X'"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product name to search for (e.g., 'mushrooms', 'champignons')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10)",
                },
            },
            "required": ["query"],
        },
        handler=lambda **kwargs: _search_products(settings, **kwargs),
    )

    registry.register(
        name="get_recent_products",
        description="Get recently purchased products (last N days)",
        parameters={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Look back N days (default 7)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                },
            },
        },
        handler=lambda **kwargs: _get_recent_products(settings, **kwargs),
    )

    registry.register(
        name="get_smart_shopping_list",
        description=(
            "Get smart shopping suggestions ranked by urgency — items you're likely "
            "running low on based on purchase patterns"
        ),
        parameters={
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "Language for product names: 'nl', 'en', or 'ru' (default: nl)",
                },
            },
        },
        handler=lambda **kwargs: _get_smart_shopping_list(settings, **kwargs),
    )
