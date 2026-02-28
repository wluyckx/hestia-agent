"""
Chat SSE streaming endpoint.

Streams Claude responses as Server-Sent Events.
PWA contract: src/lib/api/agent.ts — streamChat / ChatSSEChunk
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

import aiosqlite
import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models import ChatRequest

router = APIRouter(tags=["chat"])

SYSTEM_PROMPT = (
    "You are Hestia, a helpful personal assistant for a Belgian family. "
    "You help with meal planning, shopping, energy monitoring, and daily life. "
    "Be concise, friendly, and practical. Respond in the same language the user writes in."
)


async def _ensure_conversation(
    db: aiosqlite.Connection,
    conversation_id: str,
    user: str,
    first_message: str,
) -> None:
    """Create conversation if it doesn't exist. Auto-title from first message."""
    cursor = await db.execute(
        "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user),
    )
    if await cursor.fetchone():
        return

    now = datetime.now(UTC).isoformat()
    title = first_message[:50].strip()
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conversation_id, user, title, now, now),
    )
    await db.commit()


async def _persist_message(
    db: aiosqlite.Connection,
    conversation_id: str,
    role: str,
    content: str,
) -> str:
    """Insert a message and update conversation timestamp. Returns message ID."""
    msg_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    await db.execute(
        "INSERT INTO messages (id, conversation_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (msg_id, conversation_id, role, content, now),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )
    await db.commit()
    return msg_id


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: Annotated[str, Depends(get_current_user)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Stream a Claude response as SSE.

    SSE format: data: {"token":"...", "done":false, "conversation_id":"..."}\n\n
    Final chunk: data: {"token":"", "done":true, "conversation_id":"...", "message_id":"..."}\n\n
    """
    await _ensure_conversation(db, body.conversation_id, user, body.message)
    await _persist_message(db, body.conversation_id, "user", body.message)

    # Build messages for Claude
    messages = [{"role": h.role, "content": h.content} for h in body.history[-50:]]
    messages.append({"role": "user", "content": body.message})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def event_stream():
        full_response = ""
        try:
            async with client.messages.stream(
                model=settings.claude_model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    full_response += text
                    chunk = json.dumps(
                        {
                            "token": text,
                            "done": False,
                            "conversation_id": body.conversation_id,
                        }
                    )
                    yield f"data: {chunk}\n\n"
        except Exception as e:
            error_chunk = json.dumps(
                {
                    "token": f"Error: {e}",
                    "done": True,
                    "conversation_id": body.conversation_id,
                }
            )
            yield f"data: {error_chunk}\n\n"
            return

        msg_id = await _persist_message(db, body.conversation_id, "agent", full_response)
        done_chunk = json.dumps(
            {
                "token": "",
                "done": True,
                "conversation_id": body.conversation_id,
                "message_id": msg_id,
            }
        )
        yield f"data: {done_chunk}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
