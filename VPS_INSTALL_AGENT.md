# VPS Install Instructions — Hestia Agent Service

## Prerequisites

These should already be in place from `setup-vps.sh` (in the PWA repo at `infra/vps/`):

- Docker + Docker Compose on VPS
- Docker network `edge` exists (`docker network create edge`)
- `/home/deploy/apps/hestia-agent/` directory exists
- `docker-compose.yml` deployed (from `infra/vps/agent-service/`)
- Caddy configured with `Caddyfile.hestia` and `caddy-secrets.env`

## Step 1: Generate a bcrypt password hash (local machine)

```bash
python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('YOUR_PASSWORD_HERE'))"
```

Save the output — you'll need it in Step 2.

## Step 2: Configure `.env` on VPS

```bash
ssh deploy@<VPS_IP>
nano /home/deploy/apps/hestia-agent/.env
```

Required values:

```env
JWT_SECRET=<same-value-as-caddy-secrets.env>
POC_USERNAME=hestia
POC_PASSWORD_HASH=<bcrypt-hash-from-step-1>
ANTHROPIC_API_KEY=sk-ant-<your-real-key>
WHISPER_BASE_URL=http://100.64.168.106:9000
DATABASE_PATH=/app/data/hestia.db
```

> **Critical**: `JWT_SECRET` must match the value in `/home/deploy/infra/caddy/caddy-secrets.env`. Caddy's forward-auth validates JWTs issued by this service — a mismatch means all `/api/*` requests fail with 401.

## Step 3: Pull and start the container

```bash
cd /home/deploy/apps/hestia-agent
docker compose pull
docker compose up -d
```

## Step 4: Verify

```bash
# Health check (inside container)
docker compose exec agent-api curl -f http://localhost:8000/health
# Expected: {"status":"ok"}

# Check logs
docker compose logs -f agent-api

# Test login through Caddy
curl -X POST https://hestia.wimluyckx.dev/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"hestia","password":"YOUR_PASSWORD_HERE"}'
# Expected: {"access_token":"...","token_type":"bearer","expires_in":3600,"refresh_token":"..."}

# Test forward-auth (should return 401 without token)
curl -v https://hestia.wimluyckx.dev/api/agent/greeting
# Expected: 401

# Test with token
TOKEN=$(curl -s -X POST https://hestia.wimluyckx.dev/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"hestia","password":"YOUR_PASSWORD_HERE"}' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" https://hestia.wimluyckx.dev/api/agent/greeting
# Expected: {"greeting":"Good morning/afternoon/evening","energy":{...},...}
```

## Step 5: Build Docker image (first time only)

CI auto-builds and pushes `ghcr.io/wluyckx/hestia-agent:latest` on every push to main. For the first deployment before CI has run, build manually:

```bash
# On local machine
cd ~/hestia-agent
docker build -t ghcr.io/wluyckx/hestia-agent:latest .
docker push ghcr.io/wluyckx/hestia-agent:latest
```

> ghcr.io requires `docker login ghcr.io -u wluyckx` with a PAT that has `write:packages` scope.

## Updating

```bash
ssh deploy@<VPS_IP>
cd /home/deploy/apps/hestia-agent
docker compose pull
docker compose up -d
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `docker compose pull` fails | Image not pushed to ghcr.io yet | Build and push manually (Step 5) or wait for CI |
| Login returns 401 | Wrong password or hash mismatch | Re-generate bcrypt hash, update `.env`, restart |
| Forward-auth 502 | Agent container not running | `docker compose up -d`, check logs |
| Chat returns error | Missing/invalid `ANTHROPIC_API_KEY` | Update `.env`, restart container |
| Whisper 502 | Tailscale not connected or whisper not running | Check `tailscale status`, verify whisper at `http://100.64.168.106:9000/health` |
| All `/api/*` routes 401 | `JWT_SECRET` mismatch between agent and Caddy | Ensure both `.env` files use the same value, restart both |
