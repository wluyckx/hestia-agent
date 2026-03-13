"""
Cooking-mode tools — timer creation via agent tool-use.

CHANGELOG:
- 2026-03-13: Initial creation (STORY-067)
"""

from app.tools.registry import ToolRegistry


async def _set_cooking_timer(
    duration_minutes: float,
    name: str = "Timer",
) -> dict:
    """Create a cooking timer with the given name and duration.

    Returns structured data that the PWA uses to create a UI timer.
    """
    duration_seconds = int(duration_minutes * 60)
    return {
        "created": True,
        "name": name,
        "duration_minutes": duration_minutes,
        "duration_seconds": duration_seconds,
    }


def register_cooking_tools(registry: ToolRegistry) -> None:
    """Register cooking-mode tools in the given registry."""
    registry.register(
        name="set_cooking_timer",
        description=(
            "Set a cooking timer. Use when the user asks to set a timer, "
            "e.g. 'set a timer for 15 minutes for the sauce'. "
            "Returns confirmation with timer details."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Timer label, e.g. 'Sauce', 'Pasta'",
                },
                "duration_minutes": {
                    "type": "number",
                    "description": "Duration in minutes",
                },
            },
            "required": ["duration_minutes"],
        },
        handler=_set_cooking_timer,
    )
