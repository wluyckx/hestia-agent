"""
Mealie tools — search recipes, meal plans, shopping lists, and write operations.

Registers eight tools with the ToolRegistry for Claude tool-use:
  Read tools:
  - search_recipes: search by name, ingredient, or tag
  - get_meal_plan: current week's planned meals
  - get_shopping_list: active shopping list items
  - get_recipe_detail: full recipe with ingredients and steps
  Write tools:
  - create_meal_plan_entry: add a meal plan entry for a date
  - add_to_shopping_list: add an item to the active shopping list
  - remove_from_shopping_list: check off / remove a shopping list item
  - import_recipe_from_url: import a recipe via Mealie's scraper

CHANGELOG:
- 2026-03-12: Fix slug/ID mismatch — import returns recipe ID, create resolves slug→ID,
  search and detail include recipe ID (URL-to-planner flow)
- 2026-02-28: Add four write tools (STORY-039)
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
                        "id": r.get("id", ""),
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
                "id": data.get("id", ""),
                "name": data.get("name", ""),
                "slug": data.get("slug", ""),
                "description": data.get("description", ""),
                "ingredients": ingredients,
                "steps": steps,
                "total_time": data.get("totalTime", ""),
                "servings": data.get("recipeYield", data.get("servings", 0)),
            }
    except Exception:
        logger.warning("Recipe detail fetch failed", exc_info=True)
        return {"error": "Recipe not found"}


async def _resolve_recipe_id(
    client: httpx.AsyncClient, settings: Settings, recipe_slug: str
) -> str | None:
    """Resolve a recipe slug to its UUID by fetching the recipe."""
    try:
        resp = await client.get(
            f"{settings.mealie_base_url}/api/recipes/{recipe_slug}",
            headers=_headers(settings),
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception:
        logger.warning("Recipe ID resolve failed for slug=%s", recipe_slug, exc_info=True)
        return None


async def _create_meal_plan_entry(
    settings: Settings, *, date: str, entry_type: str, recipe_slug: str
) -> dict:
    """Create a meal plan entry for a specific date and meal type."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            recipe_id = await _resolve_recipe_id(client, settings, recipe_slug)
            if not recipe_id:
                return {"error": f"Recipe not found: {recipe_slug}"}
            resp = await client.post(
                f"{settings.mealie_base_url}/api/households/mealplans",
                headers=_headers(settings),
                json={
                    "date": date,
                    "entryType": entry_type,
                    "recipeId": recipe_id,
                },
            )
            resp.raise_for_status()
            return {
                "success": True,
                "date": date,
                "entry_type": entry_type,
                "recipe_slug": recipe_slug,
                "recipe_id": recipe_id,
            }
    except Exception:
        logger.warning("Create meal plan entry failed", exc_info=True)
        return {"error": "Failed to create meal plan entry"}


async def _add_to_shopping_list(settings: Settings, *, note: str, quantity: float = 1) -> dict:
    """Add an item to the active Mealie shopping list."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Step 1: get first shopping list ID
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
                return {"error": "Failed to add item to shopping list"}

            first = items_list[0] if isinstance(items_list, list) else items_list
            list_id = first.get("id", "")

            # Step 2: add item to that list
            resp = await client.post(
                f"{settings.mealie_base_url}/api/households/shopping/lists/{list_id}/items",
                headers=_headers(settings),
                json={"note": note, "quantity": quantity},
            )
            resp.raise_for_status()
            return {"success": True, "item": note, "list_id": list_id}
    except Exception:
        logger.warning("Add to shopping list failed", exc_info=True)
        return {"error": "Failed to add item to shopping list"}


async def _remove_from_shopping_list(settings: Settings, *, item_id: str) -> dict:
    """Check off / remove an item from the Mealie shopping list."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                f"{settings.mealie_base_url}/api/households/shopping/lists/items/{item_id}",
                headers=_headers(settings),
            )
            resp.raise_for_status()
            return {"success": True, "removed_item_id": item_id}
    except Exception:
        logger.warning("Remove from shopping list failed", exc_info=True)
        return {"error": "Failed to remove item"}


async def _import_recipe_from_url(settings: Settings, *, url: str) -> dict:
    """Import a recipe from a URL using Mealie's scraper, then fetch the recipe ID."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.mealie_base_url}/api/recipes/create-url",
                headers=_headers(settings),
                json={"url": url, "includeTags": False},
            )
            resp.raise_for_status()
            slug = resp.json()
            # Fetch the imported recipe to get its UUID
            recipe_id = await _resolve_recipe_id(client, settings, slug)
            return {"success": True, "slug": slug, "id": recipe_id or ""}
    except Exception:
        logger.warning("Import recipe from URL failed", exc_info=True)
        return {"error": "Failed to import recipe"}


def register_mealie_tools(registry: ToolRegistry, settings: Settings) -> None:
    """Register all Mealie tools (read + write) with the given registry."""
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

    registry.register(
        name="create_meal_plan_entry",
        description=(
            "Create a meal plan entry for a specific date and meal type. "
            "Describe the action before executing."
        ),
        parameters={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
                "entry_type": {
                    "type": "string",
                    "description": "Meal type: breakfast, lunch, dinner, or side",
                },
                "recipe_slug": {
                    "type": "string",
                    "description": "Recipe slug to assign",
                },
            },
            "required": ["date", "entry_type", "recipe_slug"],
        },
        handler=lambda **kwargs: _create_meal_plan_entry(settings, **kwargs),
    )

    registry.register(
        name="add_to_shopping_list",
        description=(
            "Add an item to the active Mealie shopping list. Describe the action before executing."
        ),
        parameters={
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "Item description (e.g., 'Milk 1L')",
                },
                "quantity": {
                    "type": "number",
                    "description": "Quantity (default 1)",
                },
            },
            "required": ["note"],
        },
        handler=lambda **kwargs: _add_to_shopping_list(settings, **kwargs),
    )

    registry.register(
        name="remove_from_shopping_list",
        description="Check off / remove an item from the Mealie shopping list",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "Shopping list item ID to remove",
                },
            },
            "required": ["item_id"],
        },
        handler=lambda **kwargs: _remove_from_shopping_list(settings, **kwargs),
    )

    registry.register(
        name="import_recipe_from_url",
        description=(
            "Import a recipe from a URL using Mealie's scraper. "
            "Describe the action before executing."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the recipe to import",
                },
            },
            "required": ["url"],
        },
        handler=lambda **kwargs: _import_recipe_from_url(settings, **kwargs),
    )
