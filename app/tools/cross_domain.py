"""
Cross-domain tools — orchestrate data across multiple backend services.

CHANGELOG:
- 2026-02-28: Initial creation — generate_shopping_list_from_meal_plan (STORY-040)
"""

import logging
from collections import defaultdict

import httpx

from app.config import Settings
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


def _headers(settings: Settings) -> dict:
    return {"Authorization": f"Bearer {settings.mealie_token}"}


async def _generate_shopping_list_from_meal_plan(settings: Settings) -> dict:
    """Read the meal plan, fetch each recipe's ingredients, consolidate, and create a list.

    Steps:
    1. GET today's meal plan from Mealie
    2. For each recipe, GET full recipe detail to extract ingredients
    3. Consolidate duplicate ingredients
    4. POST a new shopping list with all consolidated ingredients

    Returns a summary of what was created.
    """
    if not settings.mealie_token:
        return {"error": "Mealie not configured"}

    base = settings.mealie_base_url
    hdrs = _headers(settings)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Step 1: Get meal plan
            resp = await client.get(
                f"{base}/api/households/mealplans/today",
                headers=hdrs,
            )
            resp.raise_for_status()
            meals = resp.json()
            if not isinstance(meals, list):
                meals = [meals]

            # Collect recipe slugs
            recipe_slugs = []
            recipe_names = []
            for meal in meals:
                recipe = meal.get("recipe") or {}
                slug = recipe.get("slug")
                name = recipe.get("name", "Unknown")
                if slug:
                    recipe_slugs.append(slug)
                    recipe_names.append(name)

            if not recipe_slugs:
                return {"error": "No recipes found in today's meal plan"}

            # Step 2: Fetch each recipe's ingredients
            # {ingredient_text: [recipe_name, ...]}
            ingredient_sources: dict[str, list[str]] = defaultdict(list)

            for slug, name in zip(recipe_slugs, recipe_names, strict=True):
                try:
                    detail_resp = await client.get(
                        f"{base}/api/recipes/{slug}",
                        headers=hdrs,
                    )
                    detail_resp.raise_for_status()
                    recipe_data = detail_resp.json()

                    ingredients = recipe_data.get("recipeIngredient", [])
                    for ing in ingredients:
                        if isinstance(ing, dict):
                            text = ing.get("note") or ing.get("display", "")
                        else:
                            text = str(ing)
                        if text.strip():
                            ingredient_sources[text.strip()].append(name)
                except Exception:
                    logger.warning("Failed to fetch recipe %s", slug)

            if not ingredient_sources:
                return {"error": "No ingredients found in recipes"}

            # Step 3: Get or create shopping list
            lists_resp = await client.get(
                f"{base}/api/households/shopping/lists",
                headers=hdrs,
            )
            lists_resp.raise_for_status()
            lists_data = lists_resp.json()
            if isinstance(lists_data, dict):
                items_list = lists_data.get("items", [])
            else:
                items_list = lists_data

            if items_list:
                first = items_list[0] if isinstance(items_list, list) else items_list
                list_id = first.get("id", "")
            else:
                # Create a new shopping list
                create_resp = await client.post(
                    f"{base}/api/households/shopping/lists",
                    headers=hdrs,
                    json={"name": "Meal Plan Shopping List"},
                )
                create_resp.raise_for_status()
                list_id = create_resp.json().get("id", "")

            # Step 4: Add consolidated ingredients
            added_items = []
            for ingredient, sources in ingredient_sources.items():
                note = ingredient
                if len(sources) > 1:
                    note = f"{ingredient} (for {', '.join(sources)})"
                try:
                    await client.post(
                        f"{base}/api/households/shopping/lists/{list_id}/items",
                        headers=hdrs,
                        json={"note": note, "quantity": 1},
                    )
                    added_items.append(
                        {
                            "ingredient": ingredient,
                            "recipes": sources,
                        }
                    )
                except Exception:
                    logger.warning("Failed to add %s to list", ingredient)

            return {
                "success": True,
                "list_id": list_id,
                "recipes_processed": recipe_names,
                "items_added": len(added_items),
                "items": added_items,
            }

    except Exception:
        logger.warning("Failed to generate shopping list from meal plan", exc_info=True)
        return {"error": "Failed to generate shopping list from meal plan"}


def register_cross_domain_tools(registry: ToolRegistry, settings: Settings) -> None:
    """Register cross-domain tools."""

    async def handler() -> dict:
        return await _generate_shopping_list_from_meal_plan(settings)

    registry.register(
        name="generate_shopping_list_from_meal_plan",
        description=(
            "Read the current meal plan, extract all recipe ingredients, "
            "consolidate duplicates, and create a Mealie shopping list. "
            "Describe the action before executing."
        ),
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )
