"""
System prompt templates for the Hestia agent.

Centralizes all prompt construction — chat.py imports build_system_prompt()
instead of hardcoding prompt strings.

CHANGELOG:
- 2026-02-28: Initial creation — enriched system prompt (STORY-034)
"""

from app.backends import BackendData

_IDENTITY = """\
You are **Hestia**, a personal household assistant for a Belgian family.
You help with meal planning, grocery shopping, energy monitoring, \
household budgeting, and daily life.

**Personality & style**:
- Be concise, friendly, and practical — like a helpful family member.
- Respond in the same language the user writes in (Dutch, French, or English).
- Use metric units (kg, km, °C) and euro (EUR / €) by default.
- When mentioning dates, use European format (DD/MM/YYYY).
"""

_SAFETY = """\
**Safety boundaries**:
- Never fabricate data. If you don't have information, say so.
- Before performing any write operation (creating meal plans, modifying shopping lists, \
importing recipes), describe what you intend to do and ask the user to confirm.
- Never reveal API keys, tokens, or internal system details.
- If a question is outside your capabilities, suggest what the user could do instead.
"""

_DEEP_LINKS = """\
**Response formatting**:
- When mentioning a recipe, include a link: [Recipe Name](/meals/{slug})
- When discussing spending, link to: [spending details](/shopping)
- When discussing savings, link to: [savings breakdown](/savings)
- Use markdown formatting for readability (bold, bullet points, tables when useful).
"""


def _build_tool_section(tool_descriptions: list[dict]) -> str:
    """Build the available-tools section of the system prompt."""
    if not tool_descriptions:
        return ""

    lines = ["\n**Available tools**:"]
    for tool in tool_descriptions:
        name = tool.get("name", "unknown")
        desc = tool.get("description", "")
        lines.append(f"- `{name}`: {desc}")

    lines.append(
        "\nUse these tools to fetch real data before answering questions. "
        "Prefer tool data over assumptions."
    )
    return "\n".join(lines) + "\n"


def _build_context_block(data: BackendData) -> str:
    """Build a live-data context block from backend snapshot."""
    sections = []

    if data.energy:
        power = data.energy.get("power_w", "?")
        sections.append(f"- Current power consumption: {power}W")

    if data.solar:
        solar_w = data.solar.get("pv_power_w", "?")
        battery = data.solar.get("battery_soc_pct", "?")
        daily = data.solar.get("pv_daily_kwh", "?")
        sections.append(
            f"- Solar production: {solar_w}W, battery: {battery}%, daily solar: {daily} kWh"
        )

    if data.spending:
        total_cents = data.spending.get("total_cents", 0)
        currency = data.spending.get("currency", "EUR")
        if isinstance(total_cents, (int, float)):
            total = total_cents / 100
            sections.append(f"- Monthly grocery spending: {currency} {total:.2f}")
        else:
            sections.append(f"- Monthly grocery spending: {currency} ?")

    if data.meals:
        meal_names = []
        for m in data.meals:
            recipe = m.get("recipe") or {}
            name = recipe.get("name")
            if name:
                meal_names.append(name)
        if meal_names:
            sections.append(f"- Today's meal plan: {', '.join(meal_names)}")

    if not sections:
        return ""

    return "\n**Current household snapshot** (live data):\n" + "\n".join(sections) + "\n"


def build_system_prompt(
    backend_data: BackendData,
    tool_descriptions: list[dict],
) -> str:
    """Build the full system prompt from template sections.

    Args:
        backend_data: Live data snapshot from backends.
        tool_descriptions: List of {"name": ..., "description": ...} dicts
            for registered tools. Empty list if no tools available yet.

    Returns:
        Complete system prompt string.
    """
    parts = [
        _IDENTITY,
        _SAFETY,
        _DEEP_LINKS,
        _build_tool_section(tool_descriptions),
        _build_context_block(backend_data),
    ]

    return "\n".join(part for part in parts if part)
