"""
Greeting endpoint — time-aware greeting with placeholder data.

PWA contract: src/lib/api/agent.ts — GreetingResponse
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models import EnergyInfo, GreetingResponse

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
) -> GreetingResponse:
    """Return a time-aware greeting with placeholder energy/dinner/shopping data.

    Energy returns zeros, dinner and shopping return null.
    These will be wired to real backends in later phases.
    """
    return GreetingResponse(
        greeting=_time_greeting(),
        energy=EnergyInfo(power_w=0, daily_solar_kwh=0.0, battery_soc=0),
        dinner=None,
        shopping=None,
    )
