"""
System prompt templates for the Hestia agent.

Centralizes all prompt construction — chat.py imports build_system_prompt()
instead of hardcoding prompt strings.

CHANGELOG:
- 2026-02-28: Proactive greeting insights (STORY-047/048/049)
- 2026-02-28: Add preferences injection (STORY-045)
- 2026-02-28: Add greeting prompt (STORY-043)
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


def _build_preferences_section(preferences: list[dict]) -> str:
    """Build the household preferences section of the system prompt."""
    if not preferences:
        return ""

    lines = ["\n**Household preferences** (remembered):"]
    for pref in preferences:
        key = pref.get("key", "unknown")
        value = pref.get("value", "")
        lines.append(f"- {key}: {value}")

    lines.append(
        "\nUse these preferences to personalize your responses. "
        "Respect dietary restrictions and budget limits."
    )
    return "\n".join(lines) + "\n"


def build_system_prompt(
    backend_data: BackendData,
    tool_descriptions: list[dict],
    preferences: list[dict] | None = None,
) -> str:
    """Build the full system prompt from template sections.

    Args:
        backend_data: Live data snapshot from backends.
        tool_descriptions: List of {"name": ..., "description": ...} dicts
            for registered tools. Empty list if no tools available yet.
        preferences: List of {"key": ..., "value": ...} dicts for stored
            household preferences. None or empty list if none set.

    Returns:
        Complete system prompt string.
    """
    parts = [
        _IDENTITY,
        _SAFETY,
        _DEEP_LINKS,
        _build_tool_section(tool_descriptions),
        _build_preferences_section(preferences or []),
        _build_context_block(backend_data),
    ]

    return "\n".join(part for part in parts if part)


_GREETING_PROMPT = """\
You are Hestia, a Belgian household assistant. Generate a short, \
friendly greeting (2-3 sentences max) based on the time of day and \
the household data below. Mention the most relevant data points \
naturally — don't list everything.

If dinner is planned, mention it. If no dinner is planned, \
suggest a recipe based on frequently bought items or preferences.

If the household has a grocery budget preference and spending is \
above pace (i.e., more than expected for this point in the month), \
include a brief spending alert with the amount. Don't alert if \
no budget preference exists or spending is within budget.

If solar production is high or battery is above 80%, suggest \
running energy-intensive appliances. If approaching a capacity \
tariff peak, warn briefly.

Respond in English by default. Do NOT use markdown — plain text only.
"""


def _build_preferences_block(preferences: list[dict]) -> str:
    """Build a preferences context block for the greeting prompt."""
    if not preferences:
        return ""

    lines = ["\n**Household preferences**:"]
    for pref in preferences:
        lines.append(f"- {pref['key']}: {pref['value']}")
    return "\n".join(lines) + "\n"


def build_greeting_prompt(
    time_greeting: str,
    data: BackendData,
    preferences: list[dict] | None = None,
) -> str:
    """Build the prompt for Claude to generate a contextual greeting.

    Args:
        time_greeting: Static time-of-day greeting (e.g., "Good evening").
        data: Live backend data snapshot.
        preferences: List of {"key": ..., "value": ...} household prefs.

    Returns:
        User message to send to Claude for greeting generation.
    """
    context = _build_context_block(data)
    if not context:
        context = "\nNo live household data available right now.\n"

    pref_block = _build_preferences_block(preferences or [])

    return (
        f"Time greeting: {time_greeting}\n{context}{pref_block}\nGenerate a personalized greeting."
    )
