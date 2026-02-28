"""Tests for auth endpoints: login, validate, refresh."""

import pytest

from tests.conftest import auth_headers, make_access_token, make_refresh_token


@pytest.mark.asyncio
async def test_login_success(initialized_client):
    resp = await initialized_client.post(
        "/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["expires_in"] == 3600
    # Check httpOnly cookie was set
    assert "access_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_username(initialized_client):
    resp = await initialized_client.post(
        "/auth/login",
        json={"username": "wrong", "password": "testpass123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password(initialized_client):
    resp = await initialized_client.post(
        "/auth/login",
        json={"username": "testuser", "password": "wrongpass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_validate_with_valid_token(initialized_client):
    resp = await initialized_client.get("/auth/validate", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_validate_without_token(initialized_client):
    resp = await initialized_client.get("/auth/validate")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_validate_with_expired_token(initialized_client):
    token = make_access_token(expired=True)
    resp = await initialized_client.get(
        "/auth/validate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_valid_token(initialized_client):
    refresh_token = make_refresh_token()
    resp = await initialized_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "access_token" in resp.cookies


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(initialized_client):
    resp = await initialized_client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(initialized_client):
    """Ensure an access token cannot be used as a refresh token."""
    access_token = make_access_token()
    resp = await initialized_client.post(
        "/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert resp.status_code == 401
