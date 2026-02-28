"""
Mealie read-only tools — search recipes, meal plans, shopping lists.

Registers four tools with the ToolRegistry for Claude tool-use:
  - search_recipes: search by name, ingredient, or tag
  - get_meal_plan: current week's planned meals
  - get_shopping_list: active shopping list items
  - get_recipe_detail: full recipe with ingredients and steps

CHANGELOG:
- 2026-02-28: Initial creation — four read tools (STORY-037)
"""

import logging

import httpx

from app.config import Settings
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


def _headers(settings: Settings) -> dict[str, str]:
    """Build authorization headers for Mealie API calls."""
    return {"Authorization": f"Bearer {settings.mealie_token}"}


async def _search_recipes(settings: Settings, *, query: str) -> dict:
    """Search Mealie recipes by name, ingredient, or tag."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.mealie_base_url}/api/recipes",
                params={"search": query, "perPage": 10},
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            return {
                "recipes": [
                    {
                        "name": r.get("name", ""),
                        "slug": r.get("slug", ""),
                        "description": r.get("description", ""),
                    }
                    for r in items
                ]
            }
    except Exception:
        logger.warning("Recipe search failed", exc_info=True)
        return {"error": "Recipe search unavailable"}


async def _get_meal_plan(settings: Settings) -> dict:
    """Get the current week's planned meals."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.mealie_base_url}/api/households/mealplans/today",
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            entries = data if isinstance(data, list) else [data]
            return {
                "meals": [
                    {
                        "date": e.get("date", ""),
                        "entry_type": e.get("entryType", e.get("entry_type", "")),
                        "recipe_name": (e.get("recipe") or {}).get("name", ""),
                        "recipe_slug": (e.get("recipe") or {}).get("slug", ""),
                    }
                    for e in entries
                ]
            }
    except Exception:
        logger.warning("Meal plan fetch failed", exc_info=True)
        return {"error": "Meal plan unavailable"}


async def _get_shopping_list(settings: Settings) -> dict:
    """Get the active Mealie shopping list items."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Step 1: get list of shopping lists
            resp = await client.get(
                f"{settings.mealie_base_url}/api/households/shopping/lists",
                headers=_headers(settings),
            )
            resp.raise_for_status()
            lists_data = resp.json()
            if isinstance(lists_data, dict):
                items_list = lists_data.get("items", lists_data)
            else:
                items_list = lists_data
            if not items_list:
                return {"list_name": "", "items": []}

            first = items_list[0] if isinstance(items_list, list) else items_list
            list_id = first.get("id", "")

            # Step 2: get list detail
            resp = await client.get(
                f"{settings.mealie_base_url}/api/households/shopping/lists/{list_id}",
                headers=_headers(settings),
            )
            resp.raise_for_status()
            detail = resp.json()
            return {
                "list_name": detail.get("name", ""),
                "items": [
                    {
                        "note": item.get("note", ""),
                        "quantity": item.get("quantity", 0.0),
                        "checked": item.get("checked", False),
                    }
                    for item in detail.get("listItems", detail.get("items", []))
                ],
            }
    except Exception:
        logger.warning("Shopping list fetch failed", exc_info=True)
        return {"error": "Shopping list unavailable"}


async def _get_recipe_detail(settings: Settings, *, slug: str) -> dict:
    """Get full recipe details including ingredients and steps."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.mealie_base_url}/api/recipes/{slug}",
                headers=_headers(settings),
            )
            resp.raise_for_status()
            data = resp.json()
            ingredients = []
            for ing in data.get("recipeIngredient", []):
                if isinstance(ing, str):
                    ingredients.append(ing)
                elif isinstance(ing, dict):
                    ingredients.append(ing.get("display", ing.get("note", str(ing))))
            steps = []
            for step in data.get("recipeInstructions", []):
                if isinstance(step, str):
                    steps.append(step)
                elif isinstance(step, dict):
                    steps.append(step.get("text", str(step)))
            return {
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "ingredients": ingredients,
                "steps": steps,
                "total_time": data.get("totalTime", ""),
                "servings": data.get("recipeYield", data.get("servings", 0)),
            }
    except Exception:
        logger.warning("Recipe detail fetch failed", exc_info=True)
        return {"error": "Recipe not found"}


def register_mealie_tools(registry: ToolRegistry, settings: Settings) -> None:
    """Register all Mealie read tools with the given registry."""
    registry.register(
        name="search_recipes",
        description="Search Mealie recipes by name, ingredient, or tag",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
            },
            "required": ["query"],
        },
        handler=lambda **kwargs: _search_recipes(settings, **kwargs),
    )

    registry.register(
        name="get_meal_plan",
        description="Get the current week's planned meals",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=lambda **kwargs: _get_meal_plan(settings),
    )

    registry.register(
        name="get_shopping_list",
        description="Get the active Mealie shopping list items",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=lambda **kwargs: _get_shopping_list(settings),
    )

    registry.register(
        name="get_recipe_detail",
        description="Get full recipe details including ingredients and steps",
        parameters={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug from search or meal plan",
                },
            },
            "required": ["slug"],
        },
        handler=lambda **kwargs: _get_recipe_detail(settings, **kwargs),
    )
