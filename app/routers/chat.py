"""
Chat SSE streaming endpoint with Claude tool-use support.

Streams Claude responses as Server-Sent Events. When Claude requests
tool calls, the agent executes them server-side and continues the
conversation — tool execution is invisible to the frontend.

PWA contract: src/lib/api/agent.ts — streamChat / ChatSSEChunk

CHANGELOG:
- 2026-02-28: Auto-summarize long conversations (STORY-046)
- 2026-02-28: Register memory tools + inject preferences (STORY-045)
- 2026-02-28: Register shopping analytics tools in tool-use loop (STORY-038)
- 2026-02-28: Register Mealie tools in tool-use loop (STORY-037)
- 2026-02-28: Register energy tools in tool-use loop (STORY-036)
- 2026-02-28: Add tool-use loop with registry (STORY-035)
- 2026-02-28: Use build_system_prompt from prompts.py (STORY-034)
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

import aiosqlite
import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.backends import fetch_all
from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models import ChatRequest
from app.prompts import build_system_prompt
from app.tools.cross_domain import register_cross_domain_tools
from app.tools.energy import register_energy_tools
from app.tools.mealie import register_mealie_tools
from app.tools.memory import get_user_preferences, register_memory_tools
from app.tools.registry import ToolError, create_default_registry
from app.tools.shopping import register_shopping_tools

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
SUMMARIZE_THRESHOLD = 20


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


def _map_role(role: str) -> str:
    """Map PWA 'agent' role to Anthropic 'assistant'."""
    return "assistant" if role == "agent" else role


async def _get_conversation_summary(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> str | None:
    """Get stored summary for a conversation, or None."""
    cursor = await db.execute(
        "SELECT summary FROM conversations WHERE id = ?",
        (conversation_id,),
    )
    row = await cursor.fetchone()
    if row and row[0]:
        return row[0]
    return None


async def _maybe_summarize(
    db: aiosqlite.Connection,
    conversation_id: str,
    client: anthropic.AsyncAnthropic,
    settings: "Settings",
) -> None:
    """Summarize a conversation if it exceeds the threshold.

    Only summarizes once — if a summary already exists, it is replaced
    with an updated one covering all messages.
    """
    cursor = await db.execute(
        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    )
    count = (await cursor.fetchone())[0]

    if count <= SUMMARIZE_THRESHOLD:
        return

    # Fetch all messages for summarization
    cursor = await db.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    rows = await cursor.fetchall()

    # Build a transcript for Claude to summarize
    transcript_lines = []
    for row in rows:
        role_label = "User" if row[0] == "user" else "Assistant"
        transcript_lines.append(f"{role_label}: {row[1]}")
    transcript = "\n".join(transcript_lines)

    try:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=(
                "Summarize the following conversation concisely. "
                "Capture key topics, decisions, preferences mentioned, "
                "and any action items. Keep it under 200 words."
            ),
            messages=[{"role": "user", "content": transcript}],
        )

        summary = ""
        for block in response.content:
            if block.type == "text":
                summary += block.text

        if summary:
            await db.execute(
                "UPDATE conversations SET summary = ? WHERE id = ?",
                (summary, conversation_id),
            )
            await db.commit()
            logger.info(
                "Summarized conversation %s (%d messages)",
                conversation_id,
                count,
            )
    except Exception:
        logger.warning(
            "Failed to summarize conversation %s",
            conversation_id,
            exc_info=True,
        )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: Annotated[str, Depends(get_current_user)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Stream a Claude response as SSE, with tool-use support.

    SSE format: data: {"token":"...", "done":false, "conversation_id":"..."}\n\n
    Final chunk: data: {"token":"", "done":true, "conversation_id":"...", "message_id":"..."}\n\n

    Tool execution is server-side and invisible to the PWA.
    """
    await _ensure_conversation(db, body.conversation_id, user, body.message)
    await _persist_message(db, body.conversation_id, "user", body.message)

    # Fetch live backend data for system prompt
    backend_data = await fetch_all(settings)

    # Build tool registry and system prompt
    registry = create_default_registry()
    register_energy_tools(registry, settings)
    register_mealie_tools(registry, settings)
    register_shopping_tools(registry, settings)
    register_cross_domain_tools(registry, settings)
    register_memory_tools(registry, db, user)

    # Fetch stored preferences for system prompt injection
    preferences = await get_user_preferences(db, user)

    tool_defs = registry.get_definitions()
    tool_descriptions = registry.get_tool_descriptions()
    system_prompt = build_system_prompt(backend_data, tool_descriptions, preferences=preferences)

    # Build messages for Claude — prepend summary if available
    summary = await _get_conversation_summary(db, body.conversation_id)
    messages = []
    if summary:
        messages.append(
            {
                "role": "user",
                "content": f"[Previous conversation summary: {summary}]",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Understood, I have context from our previous conversation.",
            }
        )
    messages.extend({"role": _map_role(h.role), "content": h.content} for h in body.history[-50:])
    messages.append({"role": "user", "content": body.message})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def event_stream():
        nonlocal messages
        full_response = ""

        try:
            # Tool-use loop: call Claude, execute tools, repeat
            for _round in range(MAX_TOOL_ROUNDS):
                response = await client.messages.create(
                    model=settings.claude_model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    tools=tool_defs if tool_defs else anthropic.NOT_GIVEN,
                )

                # Check if Claude wants to use tools
                if response.stop_reason == "tool_use":
                    # Process all tool_use blocks in the response
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            try:
                                result = await registry.execute(block.name, block.input)
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": json.dumps(result),
                                    }
                                )
                            except ToolError as e:
                                logger.warning(
                                    "Tool %s failed: %s",
                                    block.name,
                                    e,
                                )
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": json.dumps({"error": str(e)}),
                                        "is_error": True,
                                    }
                                )

                    # Add assistant response + tool results to messages
                    messages.append(
                        {
                            "role": "assistant",
                            "content": [b.model_dump() for b in response.content],
                        }
                    )
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # No tool use — extract text and stream it
                for block in response.content:
                    if block.type == "text" and block.text:
                        full_response += block.text
                        chunk = json.dumps(
                            {
                                "token": block.text,
                                "done": False,
                                "conversation_id": body.conversation_id,
                            }
                        )
                        yield f"data: {chunk}\n\n"
                break

        except Exception as e:
            logger.exception("Chat error")
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

        # Auto-summarize if conversation is long (non-blocking best-effort)
        try:
            await _maybe_summarize(db, body.conversation_id, client, settings)
        except Exception:
            logger.warning("Summary failed for %s", body.conversation_id)

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
