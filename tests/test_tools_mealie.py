"""
Tests for Mealie tool-use tools — search, meal plan, shopping, recipe detail.

CHANGELOG:
- 2026-02-28: Initial creation — 7 tests (STORY-037)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.tools.mealie import (
    _get_meal_plan,
    _get_recipe_detail,
    _get_shopping_list,
    _search_recipes,
    register_mealie_tools,
)
from app.tools.registry import ToolRegistry


def _settings(**overrides) -> Settings:
    """Create a Settings instance with test defaults."""
    defaults = {
        "jwt_secret": "test",
        "mealie_base_url": "http://mealie:9000",
        "mealie_token": "tok-mealie",
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


class TestSearchRecipes:
    """Verify search_recipes tool."""

    @pytest.mark.asyncio
    async def test_search_recipes_success(self):
        """Mock search response with items — verify extraction."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response(
            {
                "items": [
                    {
                        "name": "Spaghetti Bolognese",
                        "slug": "spaghetti-bolognese",
                        "description": "Classic Italian pasta",
                    },
                    {
                        "name": "Chicken Curry",
                        "slug": "chicken-curry",
                        "description": "Spicy curry dish",
                    },
                ],
                "total": 2,
            }
        )

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _search_recipes(_settings(), query="pasta")

        assert "recipes" in result
        assert len(result["recipes"]) == 2
        assert result["recipes"][0]["name"] == "Spaghetti Bolognese"
        assert result["recipes"][0]["slug"] == "spaghetti-bolognese"
        assert result["recipes"][1]["name"] == "Chicken Curry"

    @pytest.mark.asyncio
    async def test_search_recipes_failure(self):
        """Verify error dict returned on failure."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response({}, status_code=500)

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _search_recipes(_settings(), query="pasta")

        assert result == {"error": "Recipe search unavailable"}


class TestGetMealPlan:
    """Verify get_meal_plan tool."""

    @pytest.mark.asyncio
    async def test_get_meal_plan_success(self):
        """Mock meal plan response — verify meal extraction."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response(
            [
                {
                    "date": "2026-02-28",
                    "entryType": "dinner",
                    "recipe": {
                        "name": "Pasta Bolognese",
                        "slug": "pasta-bolognese",
                    },
                },
                {
                    "date": "2026-02-28",
                    "entryType": "lunch",
                    "recipe": {
                        "name": "Caesar Salad",
                        "slug": "caesar-salad",
                    },
                },
            ]
        )

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_meal_plan(_settings())

        assert "meals" in result
        assert len(result["meals"]) == 2
        assert result["meals"][0]["date"] == "2026-02-28"
        assert result["meals"][0]["entry_type"] == "dinner"
        assert result["meals"][0]["recipe_name"] == "Pasta Bolognese"
        assert result["meals"][0]["recipe_slug"] == "pasta-bolognese"
        assert result["meals"][1]["recipe_name"] == "Caesar Salad"


class TestGetShoppingList:
    """Verify get_shopping_list tool."""

    @pytest.mark.asyncio
    async def test_get_shopping_list_success(self):
        """Mock lists + list detail responses — verify item extraction."""
        mock_client = AsyncMock()

        # First call: list of lists
        lists_response = _mock_response(
            {
                "items": [
                    {"id": "list-abc-123", "name": "Weekly Groceries"},
                ]
            }
        )
        # Second call: list detail
        detail_response = _mock_response(
            {
                "name": "Weekly Groceries",
                "listItems": [
                    {"note": "Tomatoes", "quantity": 4.0, "checked": False},
                    {"note": "Pasta", "quantity": 1.0, "checked": True},
                    {"note": "Olive oil", "quantity": 1.0, "checked": False},
                ],
            }
        )
        mock_client.get.side_effect = [lists_response, detail_response]

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_shopping_list(_settings())

        assert result["list_name"] == "Weekly Groceries"
        assert len(result["items"]) == 3
        assert result["items"][0]["note"] == "Tomatoes"
        assert result["items"][0]["quantity"] == 4.0
        assert result["items"][0]["checked"] is False
        assert result["items"][1]["checked"] is True


class TestGetRecipeDetail:
    """Verify get_recipe_detail tool."""

    @pytest.mark.asyncio
    async def test_get_recipe_detail_success(self):
        """Mock recipe detail — verify full extraction."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response(
            {
                "name": "Spaghetti Bolognese",
                "description": "Classic Italian pasta with meat sauce",
                "recipeIngredient": [
                    {"display": "500g spaghetti"},
                    {"display": "400g ground beef"},
                    {"note": "2 cloves garlic"},
                ],
                "recipeInstructions": [
                    {"text": "Boil pasta in salted water"},
                    {"text": "Brown the meat"},
                    {"text": "Combine and serve"},
                ],
                "totalTime": "PT45M",
                "recipeYield": 4,
            }
        )

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_recipe_detail(_settings(), slug="spaghetti-bolognese")

        assert result["name"] == "Spaghetti Bolognese"
        assert result["description"] == "Classic Italian pasta with meat sauce"
        assert len(result["ingredients"]) == 3
        assert result["ingredients"][0] == "500g spaghetti"
        assert result["ingredients"][2] == "2 cloves garlic"
        assert len(result["steps"]) == 3
        assert result["steps"][0] == "Boil pasta in salted water"
        assert result["total_time"] == "PT45M"
        assert result["servings"] == 4

    @pytest.mark.asyncio
    async def test_get_recipe_detail_not_found(self):
        """Mock 404 — verify error dict returned."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response({}, status_code=404)

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_recipe_detail(_settings(), slug="nonexistent-recipe")

        assert result == {"error": "Recipe not found"}


class TestRegisterMealieTools:
    """Verify tool registration."""

    def test_register_mealie_tools(self):
        """Verify all 4 tools appear in registry after registration."""
        registry = ToolRegistry()
        register_mealie_tools(registry, _settings())

        defs = registry.get_definitions()
        names = {d["name"] for d in defs}

        assert len(defs) == 4
        assert "search_recipes" in names
        assert "get_meal_plan" in names
        assert "get_shopping_list" in names
        assert "get_recipe_detail" in names

        # Verify search_recipes has required query param
        search_def = next(d for d in defs if d["name"] == "search_recipes")
        assert "query" in search_def["input_schema"]["properties"]
        assert "query" in search_def["input_schema"]["required"]

        # Verify get_recipe_detail has required slug param
        detail_def = next(d for d in defs if d["name"] == "get_recipe_detail")
        assert "slug" in detail_def["input_schema"]["properties"]
        assert "slug" in detail_def["input_schema"]["required"]
