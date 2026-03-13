"""
TTS proxy endpoint — forwards text-to-speech requests to Piper (OpenedAI Speech).

The browser never talks to Piper directly. This endpoint handles auth,
input validation, and streams audio back as audio/mpeg.

CHANGELOG:
- 2026-03-13: Forward language param to Piper payload (quality review)
- 2026-03-13: Initial creation (STORY-066)
"""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.config import Settings
from app.dependencies import get_current_user, get_settings

router = APIRouter(tags=["tts"])
logger = logging.getLogger(__name__)

TTS_TIMEOUT_S = 30


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: str = Field(default="alloy")
    language: str = Field(default="en")

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


@router.post("/tts")
async def text_to_speech(
    body: TTSRequest,
    user: Annotated[str, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Proxy TTS request to Piper and stream audio back."""
    piper_url = f"{settings.piper_base_url}/v1/audio/speech"

    payload = {
        "input": body.text,
        "voice": body.voice,
        "model": "tts-1",
        "response_format": "mp3",
        "language": body.language,
    }

    try:
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT_S) as client:
            piper_resp = await client.post(piper_url, json=payload)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        logger.warning("Piper TTS unavailable at %s", piper_url)
        raise HTTPException(status_code=503, detail="TTS service unavailable") from e
    except httpx.HTTPError as e:
        logger.warning("Piper TTS error: %s", e)
        raise HTTPException(status_code=503, detail="TTS service unavailable") from e

    if piper_resp.status_code != 200:
        logger.warning(
            "Piper returned status %d: %s",
            piper_resp.status_code,
            piper_resp.text[:200],
        )
        raise HTTPException(status_code=502, detail="Piper TTS returned an error")

    return Response(
        content=piper_resp.content,
        media_type="audio/mpeg",
    )
