"""Tests for the whisper transcription proxy endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_whisper_rejects_invalid_mime_type(initialized_client):
    resp = await initialized_client.post(
        "/whisper/transcribe",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers=auth_headers(),
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_whisper_rejects_oversized_file(initialized_client):
    # 11MB of zeros
    big_content = b"\x00" * (11 * 1024 * 1024)
    resp = await initialized_client.post(
        "/whisper/transcribe",
        files={"file": ("big.webm", big_content, "audio/webm")},
        headers=auth_headers(),
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_whisper_proxies_successfully(initialized_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "text": "Hello world",
        "language": "en",
        "duration": 2.5,
    }
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.whisper.httpx.AsyncClient", return_value=mock_client_instance):
        resp = await initialized_client.post(
            "/whisper/transcribe",
            files={"file": ("recording.webm", b"\x00\x01\x02", "audio/webm")},
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Hello world"
    assert data["language"] == "en"
    assert data["duration"] == 2.5


@pytest.mark.asyncio
async def test_whisper_handles_upstream_error(initialized_client):
    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(
        side_effect=httpx.RequestError("Connection refused", request=MagicMock())
    )
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.whisper.httpx.AsyncClient", return_value=mock_client_instance):
        resp = await initialized_client.post(
            "/whisper/transcribe",
            files={"file": ("recording.mp4", b"\x00\x01\x02", "audio/mp4")},
            headers=auth_headers(),
        )

    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_whisper_requires_auth(initialized_client):
    resp = await initialized_client.post(
        "/whisper/transcribe",
        files={"file": ("test.webm", b"\x00", "audio/webm")},
    )
    assert resp.status_code == 401
