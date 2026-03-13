"""
Greeting endpoint — Claude-generated contextual greeting with live data.

Fetches real energy, solar, meal plan, and shopping data from backends,
then asks Claude to generate a personalized greeting. Falls back to
static greeting if Claude call fails.

PWA contract: src/lib/api/agent.ts — GreetingResponse

CHANGELOG:
- 2026-03-13: Use /v1/daily-energy for today's import/export kWh (fix 0.0 kWh tile)
- 2026-02-28: Proactive spending alerts, energy insights, meal suggestions (STORY-047/048/049)
- 2026-02-28: Claude-generated intelligent greeting (STORY-043)
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

import aiosqlite
import anthropic
from fastapi import APIRouter, Depends

from app.backends import fetch_all
from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models import DinnerInfo, EnergyInfo, GreetingResponse, ShoppingInfo
from app.prompts import _GREETING_PROMPT, build_greeting_prompt
from app.tools.memory import get_user_preferences

router = APIRouter(tags=["greeting"])
logger = logging.getLogger(__name__)


def _time_greeting() -> str:
    """Return a time-appropriate greeting."""
    hour = datetime.now(UTC).hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


async def _generate_claude_greeting(
    settings: Settings,
    time_greeting: str,
    data: "BackendData",  # noqa: F821
    preferences: list[dict] | None = None,
) -> str | None:
    """Ask Claude to generate a contextual greeting. Returns None on failure."""
    if not settings.anthropic_api_key:
        return None

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        user_message = build_greeting_prompt(time_greeting, data, preferences=preferences)

        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=200,
            system=_GREETING_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        for block in response.content:
            if block.type == "text" and block.text:
                return block.text.strip()

    except Exception:
        logger.warning("Claude greeting generation failed", exc_info=True)

    return None


@router.get("/greeting", response_model=GreetingResponse)
async def greeting(
    _user: Annotated[str, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
) -> GreetingResponse:
    """Return a contextual greeting with live energy/dinner/shopping data.

    Fetches from backends concurrently. Generates greeting via Claude
    with proactive alerts for spending, energy, and meal suggestions.
    Falls back to static greeting if Claude call fails.
    """
    data = await fetch_all(settings)
    static_greeting = _time_greeting()

    # Fetch user preferences for proactive alerts
    preferences = await get_user_preferences(db, _user)

    # Try Claude-generated greeting, fall back to static
    greeting_text = await _generate_claude_greeting(
        settings, static_greeting, data, preferences=preferences
    )
    if not greeting_text:
        greeting_text = static_greeting

    # Energy: merge P1 realtime + daily-energy + solar data
    power_w = 0
    daily_solar_kwh = 0.0
    battery_soc = 0
    energy_import_kwh = 0.0
    energy_export_kwh = 0.0
    if data.energy:
        power_w = data.energy.get("power_w", 0)
    if data.daily_energy:
        energy_import_kwh = data.daily_energy.get("import_today_kwh", 0.0)
        energy_export_kwh = data.daily_energy.get("export_today_kwh", 0.0)
    if data.solar:
        daily_solar_kwh = data.solar.get("pv_daily_kwh", 0.0)
        battery_soc = data.solar.get("battery_soc_pct", 0)
        if not data.energy:
            power_w = data.solar.get("pv_power_w", 0)

    energy = EnergyInfo(
        power_w=power_w,
        daily_solar_kwh=daily_solar_kwh,
        battery_soc=battery_soc,
        energy_import_kwh=energy_import_kwh,
        energy_export_kwh=energy_export_kwh,
    )

    # Dinner: first meal plan entry with a recipe
    dinner = None
    if data.meals:
        for m in data.meals:
            recipe = m.get("recipe")
            if recipe and recipe.get("name"):
                dinner = DinnerInfo(
                    name=recipe["name"],
                    slug=recipe.get("slug", ""),
                )
                break

    # Shopping: monthly spending
    shopping = None
    if data.spending:
        total_cents = data.spending.get("total_cents", 0)
        currency = data.spending.get("currency", "EUR")
        shopping = ShoppingInfo(
            monthly_total=total_cents / 100 if isinstance(total_cents, (int, float)) else 0.0,
            currency=currency,
        )

    return GreetingResponse(
        greeting=greeting_text,
        energy=energy,
        dinner=dinner,
        shopping=shopping,
    )
