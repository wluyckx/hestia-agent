"""
Application configuration via environment variables.

Uses pydantic-settings for validation and type coercion.
All secrets loaded from environment — never hardcoded.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Agent service configuration. All values from env vars or .env file."""

    # JWT (env var: JWT_SECRET — matches Caddy secrets convention)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # POC single-user auth
    poc_username: str = "hestia"
    poc_password_hash: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Whisper
    whisper_base_url: str = "http://whisper:9000"

    # Database
    database_path: str = "data/hestia.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
