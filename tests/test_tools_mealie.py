"""
Tests for Mealie tool-use tools — read + write operations.

CHANGELOG:
- 2026-03-12: Update tests for slug/ID resolution fixes (URL-to-planner flow)
- 2026-02-28: Add write tool tests (STORY-039)
- 2026-02-28: Initial creation — 7 tests (STORY-037)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.tools.mealie import (
    _add_to_shopping_list,
    _create_meal_plan_entry,
    _get_meal_plan,
    _get_recipe_detail,
    _get_shopping_list,
    _import_recipe_from_url,
    _remove_from_shopping_list,
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
                        "id": "uuid-spag-001",
                        "name": "Spaghetti Bolognese",
                        "slug": "spaghetti-bolognese",
                        "description": "Classic Italian pasta",
                    },
                    {
                        "id": "uuid-curry-002",
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
        assert result["recipes"][0]["id"] == "uuid-spag-001"
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
                "id": "uuid-spag-001",
                "name": "Spaghetti Bolognese",
                "slug": "spaghetti-bolognese",
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

        assert result["id"] == "uuid-spag-001"
        assert result["name"] == "Spaghetti Bolognese"
        assert result["slug"] == "spaghetti-bolognese"
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


class TestCreateMealPlanEntry:
    """Verify create_meal_plan_entry tool."""

    @pytest.mark.asyncio
    async def test_create_meal_plan_entry_with_recipe(self):
        """Mock GET (slug→ID) + POST — verify resolved ID in body."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response(
            {"id": "uuid-spag-001", "name": "Spaghetti Bolognese", "slug": "spaghetti-bolognese"}
        )
        mock_client.post.return_value = _mock_response({"id": "plan-123"})

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _create_meal_plan_entry(
                _settings(),
                date="2026-03-01",
                entry_type="dinner",
                recipe_slug="spaghetti-bolognese",
            )

        assert result == {
            "success": True,
            "date": "2026-03-01",
            "entry_type": "dinner",
            "recipe_slug": "spaghetti-bolognese",
            "recipe_id": "uuid-spag-001",
        }
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["json"] == {
            "date": "2026-03-01",
            "entryType": "dinner",
            "recipeId": "uuid-spag-001",
        }

    @pytest.mark.asyncio
    async def test_create_meal_plan_entry_with_title(self):
        """Text-only entry when no recipe is linked (e.g. import failed)."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _mock_response({"id": "plan-456"})

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _create_meal_plan_entry(
                _settings(),
                date="2026-03-13",
                entry_type="lunch",
                title="Italiaanse mini croques",
            )

        assert result == {
            "success": True,
            "date": "2026-03-13",
            "entry_type": "lunch",
            "title": "Italiaanse mini croques",
        }
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["json"] == {
            "date": "2026-03-13",
            "entryType": "lunch",
            "title": "Italiaanse mini croques",
        }

    @pytest.mark.asyncio
    async def test_create_meal_plan_entry_no_slug_or_title(self):
        """Error when neither recipe_slug nor title provided."""
        result = await _create_meal_plan_entry(
            _settings(),
            date="2026-03-01",
            entry_type="dinner",
        )
        assert result == {"error": "Either recipe_slug or title is required"}

    @pytest.mark.asyncio
    async def test_create_meal_plan_entry_slug_not_found(self):
        """Verify error when slug cannot be resolved to an ID."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response({}, status_code=404)

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _create_meal_plan_entry(
                _settings(),
                date="2026-03-01",
                entry_type="dinner",
                recipe_slug="nonexistent",
            )

        assert result == {"error": "Recipe not found: nonexistent"}

    @pytest.mark.asyncio
    async def test_create_meal_plan_entry_post_failure(self):
        """Verify error dict when POST fails after successful slug resolve."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response(
            {"id": "uuid-001", "name": "Test", "slug": "test"}
        )
        mock_client.post.return_value = _mock_response({}, status_code=500)

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _create_meal_plan_entry(
                _settings(),
                date="2026-03-01",
                entry_type="dinner",
                recipe_slug="test",
            )

        assert result == {"error": "Failed to create meal plan entry"}


class TestAddToShoppingList:
    """Verify add_to_shopping_list tool."""

    @pytest.mark.asyncio
    async def test_add_to_shopping_list_success(self):
        """Mock GET lists + POST item — verify two-step flow."""
        mock_client = AsyncMock()

        # First call: GET lists
        lists_response = _mock_response(
            {"items": [{"id": "list-abc-123", "name": "Weekly Groceries"}]}
        )
        # Second call: POST item
        item_response = _mock_response({"id": "item-456", "note": "Milk 1L"})
        mock_client.get.return_value = lists_response
        mock_client.post.return_value = item_response

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _add_to_shopping_list(_settings(), note="Milk 1L", quantity=2)

        assert result == {
            "success": True,
            "item": "Milk 1L",
            "list_id": "list-abc-123",
        }
        mock_client.get.assert_called_once()
        mock_client.post.assert_called_once()
        post_kwargs = mock_client.post.call_args
        assert post_kwargs.kwargs["json"] == {"note": "Milk 1L", "quantity": 2}

    @pytest.mark.asyncio
    async def test_add_to_shopping_list_failure(self):
        """Verify error dict when no lists found."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_response({"items": []})

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _add_to_shopping_list(_settings(), note="Milk 1L")

        assert result == {"error": "Failed to add item to shopping list"}


class TestRemoveFromShoppingList:
    """Verify remove_from_shopping_list tool."""

    @pytest.mark.asyncio
    async def test_remove_from_shopping_list_success(self):
        """Mock DELETE — verify success response."""
        mock_client = AsyncMock()
        mock_client.delete.return_value = _mock_response(None)

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _remove_from_shopping_list(_settings(), item_id="item-789")

        assert result == {"success": True, "removed_item_id": "item-789"}
        mock_client.delete.assert_called_once()
        call_args = mock_client.delete.call_args
        assert "items/item-789" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_remove_from_shopping_list_failure(self):
        """Verify error dict on 404."""
        mock_client = AsyncMock()
        mock_client.delete.return_value = _mock_response({}, status_code=404)

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _remove_from_shopping_list(_settings(), item_id="nonexistent")

        assert result == {"error": "Failed to remove item"}


class TestImportRecipeFromUrl:
    """Verify import_recipe_from_url tool."""

    @pytest.mark.asyncio
    async def test_import_recipe_from_url_success(self):
        """Mock POST import + GET recipe — verify slug and ID returned."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _mock_response("imported-recipe-slug")
        # After import, resolves slug to UUID via GET
        mock_client.get.return_value = _mock_response(
            {"id": "uuid-imported-001", "name": "Imported Pasta", "slug": "imported-recipe-slug"}
        )

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _import_recipe_from_url(
                _settings(), url="https://example.com/recipe/pasta"
            )

        assert result == {
            "success": True,
            "slug": "imported-recipe-slug",
            "id": "uuid-imported-001",
        }
        mock_client.post.assert_called_once()
        post_kwargs = mock_client.post.call_args
        assert post_kwargs.kwargs["json"] == {
            "url": "https://example.com/recipe/pasta",
            "includeTags": False,
        }

    @pytest.mark.asyncio
    async def test_import_recipe_from_url_failure(self):
        """Verify error dict on API failure."""
        mock_client = AsyncMock()
        mock_client.post.return_value = _mock_response({}, status_code=500)

        with patch("app.tools.mealie.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _import_recipe_from_url(_settings(), url="https://bad.com/nope")

        assert result == {"error": "Failed to import recipe"}


class TestRegisterMealieTools:
    """Verify tool registration."""

    def test_register_mealie_tools(self):
        """Verify all 8 tools appear in registry after registration."""
        registry = ToolRegistry()
        register_mealie_tools(registry, _settings())

        defs = registry.get_definitions()
        names = {d["name"] for d in defs}

        assert len(defs) == 8
        # Read tools
        assert "search_recipes" in names
        assert "get_meal_plan" in names
        assert "get_shopping_list" in names
        assert "get_recipe_detail" in names
        # Write tools
        assert "create_meal_plan_entry" in names
        assert "add_to_shopping_list" in names
        assert "remove_from_shopping_list" in names
        assert "import_recipe_from_url" in names

        # Verify search_recipes has required query param
        search_def = next(d for d in defs if d["name"] == "search_recipes")
        assert "query" in search_def["input_schema"]["properties"]
        assert "query" in search_def["input_schema"]["required"]

        # Verify get_recipe_detail has required slug param
        detail_def = next(d for d in defs if d["name"] == "get_recipe_detail")
        assert "slug" in detail_def["input_schema"]["properties"]
        assert "slug" in detail_def["input_schema"]["required"]

        # Verify create_meal_plan_entry requires date+entry_type, slug+title optional
        mp_def = next(d for d in defs if d["name"] == "create_meal_plan_entry")
        assert set(mp_def["input_schema"]["required"]) == {"date", "entry_type"}
        assert "recipe_slug" in mp_def["input_schema"]["properties"]
        assert "title" in mp_def["input_schema"]["properties"]

        # Verify add_to_shopping_list has required note, optional quantity
        add_def = next(d for d in defs if d["name"] == "add_to_shopping_list")
        assert "note" in add_def["input_schema"]["properties"]
        assert add_def["input_schema"]["required"] == ["note"]
        assert "quantity" in add_def["input_schema"]["properties"]

        # Verify import_recipe_from_url has required url param
        import_def = next(d for d in defs if d["name"] == "import_recipe_from_url")
        assert import_def["input_schema"]["required"] == ["url"]
