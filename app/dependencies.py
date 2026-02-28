"""
FastAPI dependencies: settings, database connections, JWT auth.
"""

from functools import lru_cache
from typing import Annotated

import aiosqlite
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from app.config import Settings
from app.database import get_connection


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


async def get_db(
    settings: Annotated[Settings, Depends(get_settings)],
) -> aiosqlite.Connection:
    """Yield a database connection, closed after request."""
    db = await get_connection(settings.database_path)
    try:
        yield db  # type: ignore[misc]
    finally:
        await db.close()


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Extract and validate JWT from Authorization header or cookie.

    Returns the username (sub claim) on success, raises 401 on failure.
    """
    token: str | None = None

    # Try Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # Fall back to cookie
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if username is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        return username
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
