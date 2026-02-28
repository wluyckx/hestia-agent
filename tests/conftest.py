"""
Shared test fixtures: test client, temp database, JWT helpers.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from passlib.context import CryptContext

# Set env vars BEFORE importing app modules
_TEST_SECRET = "test-secret-key-for-testing-only-not-for-production"
_TEST_PASSWORD = "testpass123"
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_TEST_HASH = _pwd_context.hash(_TEST_PASSWORD)

os.environ.update(
    {
        "JWT_SECRET_KEY": _TEST_SECRET,
        "POC_USERNAME": "testuser",
        "POC_PASSWORD_HASH": _TEST_HASH,
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "WHISPER_BASE_URL": "http://whisper-test:9000",
        "DATABASE_PATH": "",  # overridden per test
    }
)

from app.dependencies import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def settings_override(tmp_db):
    """Override settings with test values."""
    settings = get_settings()
    original_db = settings.database_path
    settings.database_path = tmp_db
    yield settings
    settings.database_path = original_db


@pytest.fixture
async def client(tmp_db):
    """Async test client with a fresh temp database."""
    settings = get_settings()
    settings.database_path = tmp_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Trigger lifespan by making a request (lifespan auto-runs)
        yield ac


@pytest.fixture
async def initialized_client(tmp_db):
    """Async test client with DB initialized via lifespan."""
    settings = get_settings()
    settings.database_path = tmp_db

    from app.database import init_db

    await init_db(tmp_db)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def make_access_token(username: str = "testuser", expired: bool = False) -> str:
    """Create a test JWT access token."""
    delta = timedelta(hours=-1) if expired else timedelta(hours=1)
    payload = {
        "sub": username,
        "type": "access",
        "exp": datetime.now(UTC) + delta,
    }
    return jwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def make_refresh_token(username: str = "testuser", expired: bool = False) -> str:
    """Create a test JWT refresh token."""
    delta = timedelta(hours=-1) if expired else timedelta(days=7)
    payload = {
        "sub": username,
        "type": "refresh",
        "exp": datetime.now(UTC) + delta,
    }
    return jwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def auth_headers(username: str = "testuser") -> dict[str, str]:
    """Return Authorization header with a valid access token."""
    token = make_access_token(username)
    return {"Authorization": f"Bearer {token}"}
