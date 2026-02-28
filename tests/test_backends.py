"""Tests for backend API clients."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends import (
    BackendData,
    build_context_block,
    fetch_all,
    fetch_energy,
    fetch_meals,
    fetch_solar,
    fetch_spending,
)
from app.config import Settings


def _settings(**overrides) -> Settings:
    """Create a Settings instance with test defaults."""
    defaults = {
        "jwt_secret": "test",
        "energy_token": "tok-energy",
        "solar_token": "tok-solar",
        "shopping_api_key": "key-shop",
        "mealie_token": "tok-mealie",
        "energy_base_url": "http://energy:8000",
        "solar_base_url": "http://solar:8002",
        "shopping_base_url": "http://shopping:8080",
        "mealie_base_url": "http://mealie:9000",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_response(json_data, status_code=200):
    """Create a mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


@pytest.mark.asyncio
async def test_fetch_energy_success():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({"power_w": 1500, "ts": "2026-01-01T12:00:00Z"})

    with patch("app.backends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await fetch_energy(_settings())

    assert result["power_w"] == 1500


@pytest.mark.asyncio
async def test_fetch_energy_no_token():
    result = await fetch_energy(_settings(energy_token=""))
    assert result is None


@pytest.mark.asyncio
async def test_fetch_energy_failure():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({}, status_code=500)

    with patch("app.backends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await fetch_energy(_settings())

    assert result is None


@pytest.mark.asyncio
async def test_fetch_solar_success():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "pv_power_w": 3200,
            "battery_soc_pct": 85,
            "pv_daily_kwh": 12.5,
        }
    )

    with patch("app.backends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await fetch_solar(_settings())

    assert result["pv_power_w"] == 3200
    assert result["battery_soc_pct"] == 85


@pytest.mark.asyncio
async def test_fetch_spending_success():
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "total_cents": 45230,
            "currency": "EUR",
        }
    )

    with patch("app.backends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await fetch_spending(_settings())

    assert result["total_cents"] == 45230


@pytest.mark.asyncio
async def test_fetch_meals_success():
    mock_client = AsyncMock()
    meal_data = [
        {
            "date": "2026-01-15",
            "entry_type": "dinner",
            "recipe": {"name": "Pasta Bolognese", "slug": "pasta-bolognese"},
        }
    ]
    mock_client.get.return_value = _mock_response(meal_data)

    with patch("app.backends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await fetch_meals(_settings())

    assert len(result) == 1
    assert result[0]["recipe"]["name"] == "Pasta Bolognese"


@pytest.mark.asyncio
async def test_fetch_all_concurrent():
    with (
        patch("app.backends.fetch_energy", new_callable=AsyncMock) as e,
        patch("app.backends.fetch_solar", new_callable=AsyncMock) as s,
        patch("app.backends.fetch_spending", new_callable=AsyncMock) as sp,
        patch("app.backends.fetch_meals", new_callable=AsyncMock) as m,
    ):
        e.return_value = {"power_w": 1000}
        s.return_value = {
            "pv_power_w": 2000,
            "battery_soc_pct": 50,
            "pv_daily_kwh": 8.0,
        }
        sp.return_value = {"total_cents": 30000, "currency": "EUR"}
        m.return_value = [{"recipe": {"name": "Stew", "slug": "stew"}}]

        result = await fetch_all(_settings())

    assert result.energy["power_w"] == 1000
    assert result.solar["pv_power_w"] == 2000
    assert result.spending["total_cents"] == 30000
    assert result.meals[0]["recipe"]["name"] == "Stew"


def test_build_context_block_full():
    data = BackendData(
        energy={"power_w": 1500},
        solar={
            "pv_power_w": 3200,
            "battery_soc_pct": 85,
            "pv_daily_kwh": 12.5,
        },
        spending={"total_cents": 45230, "currency": "EUR"},
        meals=[{"recipe": {"name": "Pasta Bolognese"}}],
    )
    block = build_context_block(data)
    assert "1500W" in block
    assert "3200W" in block
    assert "85%" in block
    assert "452.30" in block
    assert "Pasta Bolognese" in block


def test_build_context_block_empty():
    data = BackendData()
    assert build_context_block(data) == ""


def test_build_context_block_partial():
    data = BackendData(spending={"total_cents": 10000, "currency": "EUR"})
    block = build_context_block(data)
    assert "100.00" in block
    assert "Solar" not in block
