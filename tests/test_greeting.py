"""Tests for the greeting endpoint."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_greeting_returns_morning(initialized_client):
    mock_dt = datetime(2026, 1, 15, 8, 0, 0, tzinfo=UTC)
    with patch("app.routers.greeting.datetime") as mock_datetime:
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
    with patch("app.routers.greeting.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
        resp = await initialized_client.get("/greeting", headers=auth_headers())

    assert resp.status_code == 200
    assert resp.json()["greeting"] == "Good evening"


@pytest.mark.asyncio
async def test_greeting_requires_auth(initialized_client):
    resp = await initialized_client.get("/greeting")
    assert resp.status_code == 401
