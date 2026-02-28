"""Tests for energy & solar tool handlers.

CHANGELOG:
- 2026-02-28: Add capacity tariff peak tracking tests (STORY-044)
- 2026-02-28: Initial creation — energy tool tests (STORY-036)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.tools.energy import (
    _get_capacity_peaks,
    _get_energy_realtime,
    _get_solar_status,
    _get_tariff_comparison,
    register_energy_tools,
)
from app.tools.registry import ToolRegistry


def _settings(**overrides) -> Settings:
    """Create a Settings instance with test defaults."""
    defaults = {
        "jwt_secret": "test",
        "energy_token": "tok-energy",
        "energy_base_url": "http://energy:8000",
        "energy_device_id": "dev-001",
        "solar_token": "tok-solar",
        "solar_base_url": "http://solar:8002",
        "solar_device_id": "dev-002",
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


# ---------- get_energy_realtime ----------


@pytest.mark.asyncio
async def test_get_energy_realtime_success():
    """Mock httpx returning power data, verify correct structure."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "power_w": 1500,
            "import_kwh": 12345.6,
            "export_kwh": 789.0,
            "timestamp": "2026-02-28T12:00:00Z",
        }
    )

    with patch("app.tools.energy.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_energy_realtime(_settings())

    assert result["power_w"] == 1500
    assert result["import_kwh"] == 12345.6
    assert result["export_kwh"] == 789.0
    assert result["timestamp"] == "2026-02-28T12:00:00Z"
    assert "error" not in result


@pytest.mark.asyncio
async def test_get_energy_realtime_no_token():
    """When energy_token is empty, return error dict without calling API."""
    result = await _get_energy_realtime(_settings(energy_token=""))
    assert result == {"error": "Energy data unavailable"}


@pytest.mark.asyncio
async def test_get_energy_realtime_api_failure():
    """Mock httpx raising an exception, verify error dict."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection refused")

    with patch("app.tools.energy.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_energy_realtime(_settings())

    assert result == {"error": "Energy data unavailable"}


# ---------- get_solar_status ----------


@pytest.mark.asyncio
async def test_get_solar_status_success():
    """Mock solar API response, verify correct structure."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        {
            "pv_power_w": 3200,
            "battery_soc_pct": 85,
            "pv_daily_kwh": 12.5,
            "timestamp": "2026-02-28T12:00:00Z",
        }
    )

    with patch("app.tools.energy.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_solar_status(_settings())

    assert result["pv_power_w"] == 3200
    assert result["battery_soc_pct"] == 85
    assert result["pv_daily_kwh"] == 12.5
    assert result["timestamp"] == "2026-02-28T12:00:00Z"
    assert "error" not in result


@pytest.mark.asyncio
async def test_get_solar_status_failure():
    """Verify error dict on API failure."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Timeout")

    with patch("app.tools.energy.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_solar_status(_settings())

    assert result == {"error": "Solar data unavailable"}


# ---------- get_tariff_comparison ----------


@pytest.mark.asyncio
async def test_get_tariff_comparison_success():
    """Mock tariff API response, verify JSON passthrough."""
    tariff_data = {
        "current_tariff": {"name": "EasyFix", "monthly_eur": 95.0},
        "alternatives": [
            {"name": "GreenPower", "monthly_eur": 88.5},
            {"name": "FlexRate", "monthly_eur": 91.0},
        ],
    }
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(tariff_data)

    with patch("app.tools.energy.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_tariff_comparison(_settings())

    assert result["current_tariff"]["name"] == "EasyFix"
    assert len(result["alternatives"]) == 2
    assert "error" not in result


# ---------- get_capacity_peaks ----------


@pytest.mark.asyncio
async def test_get_capacity_peaks_success():
    """Mock API returning peak data, verify it passes through."""
    peak_data = {
        "peaks": [
            {"timestamp": "2026-02-15T18:30:00Z", "kw": 5.2},
            {"timestamp": "2026-02-20T07:15:00Z", "kw": 4.8},
        ],
        "projected_annual_cost_eur": 312.50,
        "current_month_max_kw": 5.2,
    }
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(peak_data)

    with patch("app.tools.energy.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_capacity_peaks(_settings())

    assert result["peaks"] == peak_data["peaks"]
    assert result["projected_annual_cost_eur"] == 312.50
    assert result["current_month_max_kw"] == 5.2
    assert "error" not in result


@pytest.mark.asyncio
async def test_get_capacity_peaks_failure():
    """Mock API failure, verify error dict."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection refused")

    with patch("app.tools.energy.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _get_capacity_peaks(_settings())

    assert result == {"error": "Capacity peak data unavailable"}


# ---------- register_energy_tools ----------


def test_register_energy_tools():
    """Verify all 4 tools appear in registry definitions."""
    registry = ToolRegistry()
    register_energy_tools(registry, _settings())

    defs = registry.get_definitions()
    tool_names = {d["name"] for d in defs}
    assert "get_energy_realtime" in tool_names
    assert "get_solar_status" in tool_names
    assert "get_tariff_comparison" in tool_names
    assert "get_capacity_peaks" in tool_names
    assert len(defs) == 4
