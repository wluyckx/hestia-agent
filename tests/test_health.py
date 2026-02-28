"""Tests for the health endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(initialized_client):
    resp = await initialized_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
