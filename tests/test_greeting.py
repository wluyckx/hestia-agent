"""Tests for the greeting endpoint."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.backends import BackendData
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_greeting_returns_morning(initialized_client):
    mock_dt = datetime(2026, 1, 15, 8, 0, 0, tzinfo=UTC)
    mock_data = BackendData()

    with (
        patch("app.routers.greeting.datetime") as mock_datetime,
        patch("app.routers.greeting.fetch_all", new_callable=AsyncMock, return_value=mock_data),
    ):
        mock_datetime.now.return_value = mock_dt
        mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["greeting"] == "Good morning"
    assert data["energy"]["power_w"] == 0
    assert data["dinner"] is None
    assert data["shopping"] is None


@pytest.mark.asyncio
async def test_greeting_returns_evening(initialized_client):
    mock_dt = datetime(2026, 1, 15, 20, 0, 0, tzinfo=UTC)
    mock_data = BackendData()

    with (
        patch("app.routers.greeting.datetime") as mock_datetime,
        patch("app.routers.greeting.fetch_all", new_callable=AsyncMock, return_value=mock_data),
    ):
        mock_datetime.now.return_value = mock_dt
        mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    assert resp.json()["greeting"] == "Good evening"


@pytest.mark.asyncio
async def test_greeting_with_live_data(initialized_client):
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

    with (
        patch("app.routers.greeting.datetime") as mock_datetime,
        patch("app.routers.greeting.fetch_all", new_callable=AsyncMock, return_value=mock_data),
    ):
        mock_datetime.now.return_value = mock_dt
        mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["greeting"] == "Good afternoon"
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
