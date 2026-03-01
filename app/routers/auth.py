"""
Authentication endpoints: login, validate, refresh.

Issues JWTs as httpOnly cookies and in JSON body.
PWA contract: src/lib/auth/auth.ts

CHANGELOG:
- 2026-03-01: Set cookie domain for subdomain iframes (configurable via COOKIE_DOMAIN)
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models import (
    AuthError,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _create_token(data: dict, secret: str, algorithm: str, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(to_encode, secret, algorithm=algorithm)


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": AuthError}},
)
async def login(
    body: LoginRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """Authenticate with username/password. Sets httpOnly JWT cookies."""
    if body.username != settings.poc_username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not settings.poc_password_hash or not pwd_context.verify(
        body.password, settings.poc_password_hash
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_expires = timedelta(minutes=settings.access_token_expire_minutes)
    refresh_expires = timedelta(days=settings.refresh_token_expire_days)

    access_token = _create_token(
        {"sub": body.username, "type": "access"},
        settings.jwt_secret,
        settings.jwt_algorithm,
        access_expires,
    )
    refresh_token = _create_token(
        {"sub": body.username, "type": "refresh"},
        settings.jwt_secret,
        settings.jwt_algorithm,
        refresh_expires,
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain or None,
        max_age=int(access_expires.total_seconds()),
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=int(access_expires.total_seconds()),
        refresh_token=refresh_token,
    )


@router.get("/validate", status_code=200)
async def validate(user: Annotated[str, Depends(get_current_user)]) -> dict:
    """Caddy forward-auth target. Returns 200 if JWT is valid, 401 otherwise."""
    return {"username": user}


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses={401: {"model": AuthError}},
)
async def refresh(
    body: RefreshRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RefreshResponse:
    """Issue a new access token using a valid refresh token."""
    try:
        payload = jwt.decode(
            body.refresh_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        username: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if username is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    access_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = _create_token(
        {"sub": username, "type": "access"},
        settings.jwt_secret,
        settings.jwt_algorithm,
        access_expires,
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain or None,
        max_age=int(access_expires.total_seconds()),
    )

    return RefreshResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=int(access_expires.total_seconds()),
    )
