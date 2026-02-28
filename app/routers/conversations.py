"""
Conversation CRUD endpoints.

PWA contract: src/lib/api/agent.ts — listConversations, deleteConversation
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user, get_db
from app.models import (
    ConversationListResponse,
    ConversationOut,
    CreateConversationRequest,
    CreateConversationResponse,
    DeleteConversationResponse,
    MessageListResponse,
    MessageOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    user: Annotated[str, Depends(get_current_user)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
) -> ConversationListResponse:
    """List all conversations for the authenticated user, newest first."""
    cursor = await db.execute(
        "SELECT id, title, created_at, updated_at FROM conversations "
        "WHERE user_id = ? ORDER BY updated_at DESC",
        (user,),
    )
    rows = await cursor.fetchall()
    return ConversationListResponse(
        conversations=[
            ConversationOut(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
    )


@router.post("", response_model=CreateConversationResponse, status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    user: Annotated[str, Depends(get_current_user)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
) -> CreateConversationResponse:
    """Create a new conversation."""
    conv_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conv_id, user, body.title, now, now),
    )
    await db.commit()
    return CreateConversationResponse(id=conv_id, title=body.title, created_at=now, updated_at=now)


@router.delete("/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    conversation_id: str,
    user: Annotated[str, Depends(get_current_user)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
) -> DeleteConversationResponse:
    """Delete a conversation and all its messages (cascade)."""
    cursor = await db.execute(
        "DELETE FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user),
    )
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return DeleteConversationResponse(deleted=True)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: str,
    user: Annotated[str, Depends(get_current_user)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
) -> MessageListResponse:
    """List all messages in a conversation, oldest first."""
    # Verify ownership
    cursor = await db.execute(
        "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user),
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    cursor = await db.execute(
        "SELECT id, role, content, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    rows = await cursor.fetchall()
    return MessageListResponse(
        messages=[
            MessageOut(id=r["id"], role=r["role"], content=r["content"], timestamp=r["created_at"])
            for r in rows
        ]
    )
