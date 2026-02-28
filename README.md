# Hestia Agent Service

FastAPI backend for the Hestia personal assistant PWA. Provides JWT authentication, SSE streaming chat with Claude, conversation persistence, whisper transcription proxy, and a time-aware greeting endpoint.

## Quick Start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Copy and edit environment variables
cp .env.example .env

# Run tests
pytest -v

# Start dev server
uvicorn app.main:app --reload --port 8000
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Liveness check |
| POST | `/auth/login` | No | Username/password login, returns JWT |
| GET | `/auth/validate` | Yes | Caddy forward-auth target |
| POST | `/auth/refresh` | No | Refresh access token |
| POST | `/chat` | Yes | SSE streaming chat with Claude |
| GET | `/conversations` | Yes | List conversations |
| POST | `/conversations` | Yes | Create conversation |
| DELETE | `/conversations/{id}` | Yes | Delete conversation |
| GET | `/conversations/{id}/messages` | Yes | List messages |
| GET | `/greeting` | Yes | Time-aware greeting |
| POST | `/whisper/transcribe` | Yes | Proxy audio to Whisper |

## Docker

```bash
docker build -t ghcr.io/wimluyckx/hestia-agent:latest .
docker run --env-file .env -p 8000:8000 ghcr.io/wimluyckx/hestia-agent:latest
```

## Quality Gates

```bash
ruff check app/ tests/
ruff format --check app/ tests/
pytest -v
```
