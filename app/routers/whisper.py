"""
Whisper transcription proxy endpoint.

Validates audio uploads and forwards to self-hosted Whisper service.
PWA contract: src/lib/api/whisper.ts
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models import WhisperResponse

router = APIRouter(prefix="/whisper", tags=["whisper"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = {"audio/webm", "audio/mp4"}


@router.post("/transcribe", response_model=WhisperResponse)
async def transcribe(
    file: UploadFile,
    _user: Annotated[str, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WhisperResponse:
    """Accept audio upload, validate, and proxy to Whisper service."""
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Invalid audio format: {file.content_type}. Expected audio/webm or audio/mp4.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Audio file exceeds 10MB limit.",
        )

    whisper_url = f"{settings.whisper_base_url}/v1/audio/transcriptions"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                whisper_url,
                files={"file": (file.filename or "recording", content, file.content_type)},
                data={"model": "whisper-1"},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Whisper service error: {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Whisper service unavailable: {e}",
        ) from e

    data = resp.json()
    return WhisperResponse(
        text=data.get("text", ""),
        language=data.get("language", "unknown"),
        duration=data.get("duration", 0.0),
    )
