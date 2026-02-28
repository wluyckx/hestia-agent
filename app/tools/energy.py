"""
Energy & solar tool handlers for Claude tool-use.

Provides three tools:
- get_energy_realtime: real-time P1 smart meter data
- get_solar_status: solar panel production & battery status
- get_tariff_comparison: Belgian energy tariff comparison

CHANGELOG:
- 2026-02-28: Initial creation — energy tools (STORY-036)
"""

import logging

import httpx

from app.config import Settings
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


async def _get_energy_realtime(settings: Settings) -> dict:
    """Fetch real-time household power consumption from the P1 smart meter."""
    if not settings.energy_token:
        return {"error": "Energy data unavailable"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.energy_base_url}/v1/realtime",
                params={"device_id": settings.energy_device_id},
                headers={"Authorization": f"Bearer {settings.energy_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "power_w": data.get("power_w", 0),
                "import_kwh": data.get("import_kwh", 0.0),
                "export_kwh": data.get("export_kwh", 0.0),
                "timestamp": data.get("timestamp", ""),
            }
    except Exception:
        logger.warning("Failed to fetch energy realtime data", exc_info=True)
        return {"error": "Energy data unavailable"}


async def _get_solar_status(settings: Settings) -> dict:
    """Fetch current solar panel production and battery status."""
    if not settings.solar_token:
        return {"error": "Solar data unavailable"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.solar_base_url}/v1/realtime",
                params={"device_id": settings.solar_device_id},
                headers={"Authorization": f"Bearer {settings.solar_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "pv_power_w": data.get("pv_power_w", 0),
                "battery_soc_pct": data.get("battery_soc_pct", 0),
                "pv_daily_kwh": data.get("pv_daily_kwh", 0.0),
                "timestamp": data.get("timestamp", ""),
            }
    except Exception:
        logger.warning("Failed to fetch solar status", exc_info=True)
        return {"error": "Solar data unavailable"}


async def _get_tariff_comparison(settings: Settings) -> dict:
    """Fetch tariff comparison from the Belgian Energy API."""
    if not settings.energy_token:
        return {"error": "Tariff comparison unavailable"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.energy_base_url}/v1/tariffs/compare",
                params={"device_id": settings.energy_device_id},
                headers={"Authorization": f"Bearer {settings.energy_token}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.warning("Failed to fetch tariff comparison", exc_info=True)
        return {"error": "Tariff comparison unavailable"}


def register_energy_tools(registry: ToolRegistry, settings: Settings) -> None:
    """Register all energy/solar tools into the given registry.

    Uses closures to bind the settings instance into each handler so the
    registry can call them with no arguments (matching the empty parameter
    schemas).
    """

    async def energy_realtime_handler() -> dict:
        return await _get_energy_realtime(settings)

    async def solar_status_handler() -> dict:
        return await _get_solar_status(settings)

    async def tariff_comparison_handler() -> dict:
        return await _get_tariff_comparison(settings)

    registry.register(
        name="get_energy_realtime",
        description="Get real-time household power consumption from the P1 smart meter",
        parameters={"type": "object", "properties": {}},
        handler=energy_realtime_handler,
    )

    registry.register(
        name="get_solar_status",
        description="Get current solar panel production and battery status",
        parameters={"type": "object", "properties": {}},
        handler=solar_status_handler,
    )

    registry.register(
        name="get_tariff_comparison",
        description="Compare current energy tariff with alternatives from the Belgian Energy API",
        parameters={"type": "object", "properties": {}},
        handler=tariff_comparison_handler,
    )
