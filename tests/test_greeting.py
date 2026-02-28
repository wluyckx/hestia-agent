"""Tests for the greeting endpoint.

CHANGELOG:
- 2026-02-28: Add Claude greeting tests + fallback (STORY-043)
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends import BackendData
from tests.conftest import auth_headers


def _claude_text_response(text: str) -> SimpleNamespace:
    """Create a mock Claude response with a text block."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


def _patch_greeting_deps(
    mock_dt: datetime,
    mock_data: BackendData,
    claude_response=None,
    claude_error: bool = False,
):
    """Return context manager patches for greeting endpoint dependencies."""
    mock_datetime = MagicMock()
    mock_datetime.now.return_value = mock_dt
    mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)

    mock_client = MagicMock()
    mock_messages = MagicMock()
    mock_client.messages = mock_messages

    if claude_error:
        mock_messages.create = AsyncMock(side_effect=Exception("API down"))
    elif claude_response:
        mock_messages.create = AsyncMock(return_value=claude_response)
    else:
        # No API key scenario — the function returns None before calling
        mock_messages.create = AsyncMock(return_value=_claude_text_response(""))

    return (
        patch("app.routers.greeting.datetime", mock_datetime),
        patch(
            "app.routers.greeting.fetch_all",
            new_callable=AsyncMock,
            return_value=mock_data,
        ),
        patch(
            "app.routers.greeting.anthropic.AsyncAnthropic",
            return_value=mock_client,
        ),
    )


# ---- Fallback (static) greeting tests ----


@pytest.mark.asyncio
async def test_greeting_fallback_morning(initialized_client):
    """When Claude fails, fall back to static time greeting."""
    mock_dt = datetime(2026, 1, 15, 8, 0, 0, tzinfo=UTC)
    patches = _patch_greeting_deps(mock_dt, BackendData(), claude_error=True)

    with patches[0], patches[1], patches[2]:
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["greeting"] == "Good morning"
    assert data["energy"]["power_w"] == 0
    assert data["dinner"] is None
    assert data["shopping"] is None


@pytest.mark.asyncio
async def test_greeting_fallback_evening(initialized_client):
    mock_dt = datetime(2026, 1, 15, 20, 0, 0, tzinfo=UTC)
    patches = _patch_greeting_deps(mock_dt, BackendData(), claude_error=True)

    with patches[0], patches[1], patches[2]:
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    assert resp.json()["greeting"] == "Good evening"


# ---- Claude-generated greeting tests ----


@pytest.mark.asyncio
async def test_greeting_claude_generated(initialized_client):
    """Claude generates a personalized greeting from backend data."""
    mock_dt = datetime(2026, 1, 15, 19, 0, 0, tzinfo=UTC)
    mock_data = BackendData(
        energy={"power_w": 435},
        meals=[
            {
                "date": "2026-01-15",
                "entry_type": "dinner",
                "recipe": {"name": "Pasta Bolognese", "slug": "pasta-bolognese"},
            }
        ],
    )
    claude_text = "Good evening! You're using 435W right now. Tonight's dinner: Pasta Bolognese."
    patches = _patch_greeting_deps(
        mock_dt, mock_data, claude_response=_claude_text_response(claude_text)
    )

    with patches[0], patches[1], patches[2]:
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    # Greeting comes from Claude, not static
    assert data["greeting"] == claude_text
    # Structured data still populated correctly
    assert data["energy"]["power_w"] == 435
    assert data["dinner"]["name"] == "Pasta Bolognese"
    assert data["dinner"]["slug"] == "pasta-bolognese"


@pytest.mark.asyncio
async def test_greeting_claude_failure_fallback(initialized_client):
    """If Claude API fails, fall back to static greeting."""
    mock_dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    mock_data = BackendData(spending={"total_cents": 60000, "currency": "EUR"})
    patches = _patch_greeting_deps(mock_dt, mock_data, claude_error=True)

    with patches[0], patches[1], patches[2]:
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["greeting"] == "Good afternoon"
    # Structured data still populated even on Claude failure
    assert data["shopping"]["monthly_total"] == 600.00
    assert data["shopping"]["currency"] == "EUR"


# ---- Structured data tests ----


@pytest.mark.asyncio
async def test_greeting_structured_data_with_claude(initialized_client):
    """Verify all structured data fields populated correctly with Claude greeting."""
    mock_dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    mock_data = BackendData(
        energy={"power_w": 1500},
        solar={"pv_power_w": 3200, "battery_soc_pct": 85, "pv_daily_kwh": 12.5},
        spending={"total_cents": 45230, "currency": "EUR"},
        meals=[
            {
                "date": "2026-01-15",
                "entry_type": "dinner",
                "recipe": {"name": "Pasta", "slug": "pasta"},
            }
        ],
    )
    patches = _patch_greeting_deps(
        mock_dt,
        mock_data,
        claude_response=_claude_text_response("Great afternoon!"),
    )

    with patches[0], patches[1], patches[2]:
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["greeting"] == "Great afternoon!"
    assert data["energy"]["power_w"] == 1500
    assert data["energy"]["battery_soc"] == 85
    assert data["energy"]["daily_solar_kwh"] == 12.5
    assert data["dinner"]["name"] == "Pasta"
    assert data["dinner"]["slug"] == "pasta"
    assert data["shopping"]["monthly_total"] == 452.30
    assert data["shopping"]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_greeting_requires_auth(initialized_client):
    resp = await initialized_client.get("/greeting")
    assert resp.status_code == 401
