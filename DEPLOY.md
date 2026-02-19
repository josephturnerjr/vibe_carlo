# Deploying vibe_carlo

vibe_carlo runs as a Docker container on a single VPS behind a Caddy reverse proxy with automatic TLS.

## Prerequisites

- Docker installed on the VPS
- Caddy installed and managing TLS (Let's Encrypt)
- A domain name with DNS pointing to the VPS

## Environment variables

| Variable | Default (in image) | Description |
|---|---|---|
| `VIBE_CARLO_DB` | `/data/vibe_carlo.db` | Path to the SQLite database file |
| `VIBE_CARLO_SECURE_COOKIES` | `1` | Set to `1` to mark session cookies as `Secure` (always on in the production image) |

## Building the image

```bash
docker build -t vibe-carlo .
```

## Running the container

```bash
docker run -d \
  --name vibe-carlo \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v vibe-carlo-data:/data \
  vibe-carlo
```

- `-v vibe-carlo-data:/data` — persists the SQLite database across container restarts
- `-p 127.0.0.1:8000:8000` — binds only to localhost since Caddy handles external traffic
- `--restart unless-stopped` — auto-restarts on crash or reboot

## Creating your first user

```bash
docker exec vibe-carlo uv run vibe-carlo-users create user@example.com --password 'your-password'
```

## User management

```bash
# List all users
docker exec vibe-carlo uv run vibe-carlo-users list

# Change a password
docker exec vibe-carlo uv run vibe-carlo-users change-password user@example.com --password 'new-password'

# Delete a user
docker exec vibe-carlo uv run vibe-carlo-users delete user@example.com

# Assign unowned snapshots to a user
docker exec vibe-carlo uv run vibe-carlo-users assign-snapshots user@example.com
```

## Caddy configuration

Example Caddyfile snippet:

```
your-domain.com {
    reverse_proxy localhost:8000
}
```

Caddy automatically provisions and renews TLS certificates via Let's Encrypt.

## Git hook deployment

Example `post-receive` hook (on the VPS bare repo):

```bash
#!/bin/bash
set -e

WORK_DIR=/opt/vibe-carlo
CONTAINER_NAME=vibe-carlo

# Check out the latest code
git --work-tree="$WORK_DIR" --git-dir="$(pwd)" checkout -f

cd "$WORK_DIR"

# Build the new image
docker build -t vibe-carlo .

# Stop and remove the old container (data volume persists)
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Start the new container
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v vibe-carlo-data:/data \
  vibe-carlo

echo "Deploy complete."
```

## Health check

The app exposes `GET /health` which returns `{"status": "ok"}` with a 200 status code. This endpoint requires no authentication.

- **Docker** uses this via the `HEALTHCHECK` instruction in the Dockerfile (checks every 30s)
- **Caddy** can use it for upstream health checking if configured

Check container health status:

```bash
docker inspect --format='{{.State.Health.Status}}' vibe-carlo
```
