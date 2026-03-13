"""
FastAPI application entry point.

Mounts all routers and initialises the database on startup.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.dependencies import get_settings
from app.routers import auth, chat, conversations, greeting, health, tts, whisper


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialise database on startup."""
    settings = get_settings()
    os.makedirs(os.path.dirname(settings.database_path) or ".", exist_ok=True)
    await init_db(settings.database_path)
    yield


app = FastAPI(
    title="Hestia Agent Service",
    version="0.1.0",
    lifespan=lifespan,
)

# Auth router at /auth (Caddy passes through without stripping)
app.include_router(auth.router)

# All other routers at root (Caddy strips /api/agent prefix)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(greeting.router)
app.include_router(whisper.router)
app.include_router(tts.router)
