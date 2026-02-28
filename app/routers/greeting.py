"""
Greeting endpoint — time-aware greeting with live backend data.

Fetches real energy, solar, meal plan, and shopping data from backends.
Falls back to placeholder zeros if any backend is unavailable.

PWA contract: src/lib/api/agent.ts — GreetingResponse
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.backends import fetch_all
from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models import DinnerInfo, EnergyInfo, GreetingResponse, ShoppingInfo

router = APIRouter(tags=["greeting"])


def _time_greeting() -> str:
    """Return a time-appropriate greeting."""
    hour = datetime.now(UTC).hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


@router.get("/greeting", response_model=GreetingResponse)
async def greeting(
    _user: Annotated[str, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GreetingResponse:
    """Return a time-aware greeting with live energy/dinner/shopping data.

    Fetches from backends concurrently. Falls back to zeros/null on failure.
    """
    data = await fetch_all(settings)

    # Energy: merge P1 + solar data
    power_w = 0
    daily_solar_kwh = 0.0
    battery_soc = 0
    if data.energy:
        power_w = data.energy.get("power_w", 0)
    if data.solar:
        daily_solar_kwh = data.solar.get("daily_solar_kwh", 0.0)
        battery_soc = data.solar.get("battery_soc", 0)
        if not data.energy:
            power_w = data.solar.get("solar_power_w", 0)

    energy = EnergyInfo(
        power_w=power_w,
        daily_solar_kwh=daily_solar_kwh,
        battery_soc=battery_soc,
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
        greeting=_time_greeting(),
        energy=energy,
        dinner=dinner,
        shopping=shopping,
    )
