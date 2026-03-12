"""Tests for the system prompt module.

CHANGELOG:
- 2026-02-28: Add deep-link pattern verification tests (STORY-042)
- 2026-02-28: Initial creation — enriched system prompt (STORY-034)
"""

from app.backends import BackendData
from app.prompts import build_system_prompt


class TestSystemPromptSections:
    """Verify system prompt contains all required sections."""

    def test_contains_hestia_identity(self):
        prompt = build_system_prompt(BackendData(), tool_descriptions=[])
        assert "Hestia" in prompt
        assert "Belgian" in prompt or "Belgium" in prompt

    def test_contains_language_instruction(self):
        prompt = build_system_prompt(BackendData(), tool_descriptions=[])
        assert "language" in prompt.lower()

    def test_contains_safety_boundaries(self):
        prompt = build_system_prompt(BackendData(), tool_descriptions=[])
        # Must mention confirmation before writes
        assert "confirm" in prompt.lower()
        # Must mention not fabricating data
        lower = prompt.lower()
        assert "fabricat" in lower or "invent" in lower or "make up" in lower

    def test_contains_tool_listing_when_tools_provided(self):
        tools = [
            {"name": "get_energy_realtime", "description": "Get current power consumption"},
            {"name": "get_meal_plan", "description": "Get today's meal plan"},
        ]
        prompt = build_system_prompt(BackendData(), tool_descriptions=tools)
        assert "get_energy_realtime" in prompt
        assert "get_meal_plan" in prompt

    def test_no_tool_section_when_no_tools(self):
        prompt = build_system_prompt(BackendData(), tool_descriptions=[])
        # Should not mention "Available tools" section when no tools registered
        assert "Available tools" not in prompt

    def test_contains_current_date_and_weekday(self):
        prompt = build_system_prompt(BackendData(), tool_descriptions=[])
        assert "Current date" in prompt
        # Must contain a weekday name so Claude can resolve "Saturday" etc.
        weekdays = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
        assert any(day in prompt for day in weekdays)


class TestSystemPromptDataInjection:
    """Verify live data context block is injected correctly."""

    def test_includes_energy_data(self):
        data = BackendData(energy={"power_w": 1500})
        prompt = build_system_prompt(data, tool_descriptions=[])
        assert "1500" in prompt
        assert "power" in prompt.lower() or "watt" in prompt.lower() or "W" in prompt

    def test_includes_solar_data(self):
        data = BackendData(solar={"pv_power_w": 3200, "battery_soc_pct": 85, "pv_daily_kwh": 12.5})
        prompt = build_system_prompt(data, tool_descriptions=[])
        assert "3200" in prompt
        assert "85" in prompt
        assert "12.5" in prompt

    def test_includes_spending_data(self):
        data = BackendData(spending={"total_cents": 45230, "currency": "EUR"})
        prompt = build_system_prompt(data, tool_descriptions=[])
        assert "452.30" in prompt
        assert "EUR" in prompt

    def test_includes_meal_data(self):
        data = BackendData(
            meals=[
                {
                    "recipe": {"name": "Pasta Bolognese", "slug": "pasta-bolognese"},
                    "entry_type": "dinner",
                }
            ],
        )
        prompt = build_system_prompt(data, tool_descriptions=[])
        assert "Pasta Bolognese" in prompt

    def test_empty_data_no_context_block(self):
        prompt = build_system_prompt(BackendData(), tool_descriptions=[])
        assert "live data" not in prompt.lower() or "no live data" in prompt.lower()

    def test_full_data_all_sections_present(self):
        data = BackendData(
            energy={"power_w": 500},
            solar={"pv_power_w": 2000, "battery_soc_pct": 90, "pv_daily_kwh": 8.0},
            spending={"total_cents": 30000, "currency": "EUR"},
            meals=[{"recipe": {"name": "Spaghetti", "slug": "spaghetti"}, "entry_type": "dinner"}],
        )
        prompt = build_system_prompt(data, tool_descriptions=[])
        assert "500" in prompt
        assert "2000" in prompt
        assert "300.00" in prompt
        assert "Spaghetti" in prompt


class TestSystemPromptSize:
    """Verify prompt stays within reasonable token limits."""

    def test_prompt_under_4000_tokens_estimate(self):
        """Rough estimate: 1 token ≈ 4 characters. 4000 tokens ≈ 16000 chars."""
        data = BackendData(
            energy={"power_w": 1500},
            solar={"pv_power_w": 3200, "battery_soc_pct": 85, "pv_daily_kwh": 12.5},
            spending={"total_cents": 60000, "currency": "EUR"},
            meals=[
                {
                    "recipe": {"name": "Pasta Bolognese", "slug": "pasta-bolognese"},
                    "entry_type": "dinner",
                }
            ],
        )
        tools = [
            {"name": f"tool_{i}", "description": f"Description for tool {i}"} for i in range(15)
        ]
        prompt = build_system_prompt(data, tool_descriptions=tools)
        # 4000 tokens ≈ 16000 chars (conservative estimate)
        assert len(prompt) < 16000, f"System prompt too long: {len(prompt)} chars"


class TestSystemPromptConfigurability:
    """Verify prompt is built from prompts.py, not hardcoded in chat.py."""

    def test_build_system_prompt_is_callable(self):
        """Confirm the function exists and is importable from app.prompts."""
        from app.prompts import build_system_prompt

        assert callable(build_system_prompt)

    def test_returns_string(self):
        result = build_system_prompt(BackendData(), tool_descriptions=[])
        assert isinstance(result, str)
        assert len(result) > 100  # Non-trivial prompt


class TestDeepLinkPatterns:
    """Verify system prompt contains correct deep-link URL patterns (STORY-042)."""

    def _prompt(self) -> str:
        return build_system_prompt(BackendData(), tool_descriptions=[])

    def test_deep_links_recipe_pattern(self):
        """Prompt instructs Claude to link recipes using /meals/{slug}."""
        prompt = self._prompt()
        assert "/meals/" in prompt
        assert "{slug}" in prompt

    def test_deep_links_shopping_pattern(self):
        """Prompt instructs Claude to link spending details to /shopping."""
        prompt = self._prompt()
        assert "/shopping" in prompt

    def test_deep_links_savings_pattern(self):
        """Prompt instructs Claude to link savings breakdown to /savings."""
        prompt = self._prompt()
        assert "/savings" in prompt
