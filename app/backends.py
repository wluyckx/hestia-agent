"""
Backend API clients — fetch live data from Docker-network services.

Each function returns a dict or None (on failure). Failures are logged
but never block the chat response — the agent simply won't have that data.
"""

import logging
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


@dataclass
class BackendData:
    """Aggregated snapshot of all backend data for system prompt injection."""

    energy: dict | None = None
    solar: dict | None = None
    spending: dict | None = None
    meals: list | None = None


async def fetch_energy(settings: Settings) -> dict | None:
    """GET /v1/realtime from P1 energy API."""
    if not settings.energy_token:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.energy_base_url}/v1/realtime",
                headers={"Authorization": f"Bearer {settings.energy_token}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.warning("Failed to fetch energy data", exc_info=True)
        return None


async def fetch_solar(settings: Settings) -> dict | None:
    """GET /v1/realtime from Sungrow solar API."""
    if not settings.solar_token:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.solar_base_url}/v1/realtime",
                headers={"Authorization": f"Bearer {settings.solar_token}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.warning("Failed to fetch solar data", exc_info=True)
        return None


async def fetch_spending(settings: Settings) -> dict | None:
    """GET /v1/analytics/spending/monthly?months=1 from shopping API."""
    if not settings.shopping_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.shopping_base_url}/v1/analytics/spending/monthly",
                params={"months": 1},
                headers={"X-API-Key": settings.shopping_api_key},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.warning("Failed to fetch spending data", exc_info=True)
        return None


async def fetch_meals(settings: Settings) -> list | None:
    """GET /api/households/mealplans/today from Mealie."""
    if not settings.mealie_token:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.mealie_base_url}/api/households/mealplans/today",
                headers={"Authorization": f"Bearer {settings.mealie_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else [data]
    except Exception:
        logger.warning("Failed to fetch meal plan data", exc_info=True)
        return None


async def fetch_all(settings: Settings) -> BackendData:
    """Fetch all backend data concurrently. Never raises."""
    import asyncio

    energy, solar, spending, meals = await asyncio.gather(
        fetch_energy(settings),
        fetch_solar(settings),
        fetch_spending(settings),
        fetch_meals(settings),
    )
    return BackendData(energy=energy, solar=solar, spending=spending, meals=meals)


def build_context_block(data: BackendData) -> str:
    """Build a text block summarizing live data for the system prompt."""
    sections = []

    if data.energy:
        power = data.energy.get("power_w", "?")
        sections.append(f"- Current power consumption: {power}W")

    if data.solar:
        solar_w = data.solar.get("solar_power_w", "?")
        battery = data.solar.get("battery_soc", "?")
        daily = data.solar.get("daily_solar_kwh", "?")
        sections.append(
            f"- Solar production: {solar_w}W, battery: {battery}%, daily solar: {daily} kWh"
        )

    if data.spending:
        total_cents = data.spending.get("total_cents", 0)
        currency = data.spending.get("currency", "EUR")
        total = total_cents / 100 if isinstance(total_cents, (int, float)) else "?"
        sections.append(
            f"- Monthly grocery spending: {currency} {total:.2f}"
            if isinstance(total, float)
            else f"- Monthly grocery spending: {currency} {total}"
        )

    if data.meals:
        meal_names = []
        for m in data.meals:
            recipe = m.get("recipe") or {}
            name = recipe.get("name", "Unknown")
            meal_names.append(name)
        if meal_names:
            sections.append(f"- Today's meal plan: {', '.join(meal_names)}")

    if not sections:
        return ""

    return "\n\nYou have access to the following live data about the household:\n" + "\n".join(
        sections
    )
