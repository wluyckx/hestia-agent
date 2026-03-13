"""Tests for the TTS proxy endpoint.

Hestia-agent proxies text-to-speech requests to the Piper TTS container
(OpenedAI Speech) running on the VPS. The browser never talks to Piper
directly — this endpoint handles auth and audio streaming.

CHANGELOG:
- 2026-03-13: Initial creation — TDD red phase (STORY-066)
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tests.conftest import auth_headers

_MOCK_AUDIO = b"\xff\xfb\x90\x00" * 100  # fake MP3 bytes


@pytest.mark.asyncio
async def test_tts_returns_audio_stream(initialized_client):
    """POST /tts with valid text returns audio/mpeg stream."""
    mock_response = httpx.Response(
        200,
        content=_MOCK_AUDIO,
        headers={"content-type": "audio/mpeg"},
    )

    with patch(
        "app.routers.tts.httpx.AsyncClient",
    ) as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = await initialized_client.post(
            "/tts",
            json={
                "text": "Hello, dinner is ready.",
                "voice": "alloy",
                "language": "en",
            },
            headers=auth_headers(),
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_tts_requires_auth(initialized_client):
    """POST /tts without auth returns 401."""
    resp = await initialized_client.post(
        "/tts",
        json={"text": "Hello", "voice": "alloy", "language": "en"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tts_rejects_empty_text(initialized_client):
    """POST /tts with empty text returns 422."""
    resp = await initialized_client.post(
        "/tts",
        json={"text": "", "voice": "alloy", "language": "en"},
        headers=auth_headers(),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tts_rejects_long_text(initialized_client):
    """POST /tts with text over 5000 chars returns 422."""
    resp = await initialized_client.post(
        "/tts",
        json={"text": "A" * 5001, "voice": "alloy", "language": "en"},
        headers=auth_headers(),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tts_passes_voice_and_model_to_piper(initialized_client):
    """Voice and language params forwarded correctly to Piper API."""
    mock_response = httpx.Response(
        200,
        content=_MOCK_AUDIO,
        headers={"content-type": "audio/mpeg"},
    )

    with patch(
        "app.routers.tts.httpx.AsyncClient",
    ) as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        await initialized_client.post(
            "/tts",
            json={
                "text": "Goedenavond",
                "voice": "alloy",
                "language": "nl",
            },
            headers=auth_headers(),
        )

        call_kwargs = mock_instance.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["input"] == "Goedenavond"
        assert payload["voice"] == "alloy"
        assert payload["language"] == "nl"


@pytest.mark.asyncio
async def test_tts_graceful_fallback_when_piper_unavailable(initialized_client):
    """When Piper is down, return 503 with error message."""
    with patch(
        "app.routers.tts.httpx.AsyncClient",
    ) as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = await initialized_client.post(
            "/tts",
            json={"text": "Hello", "voice": "alloy", "language": "en"},
            headers=auth_headers(),
        )

    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tts_piper_error_forwarded(initialized_client):
    """When Piper returns an error, forward status."""
    mock_response = httpx.Response(
        500,
        content=b"Internal server error",
        headers={"content-type": "text/plain"},
    )

    with patch(
        "app.routers.tts.httpx.AsyncClient",
    ) as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = await initialized_client.post(
            "/tts",
            json={"text": "Hello", "voice": "alloy", "language": "en"},
            headers=auth_headers(),
        )

    assert resp.status_code == 502
    assert "piper" in resp.json()["detail"].lower()
