# Deploying vibe_carlo

vibe_carlo runs as a Docker Compose service on a single VPS behind a Caddy reverse proxy with automatic TLS. All projects on the VPS share an external Docker network (`docklinode`) so Caddy can reach each service by container name.

## Prerequisites

- Docker and Docker Compose installed on the VPS
- A `docklinode` external Docker network (`docker network create docklinode`)
- Caddy running on the same `docklinode` network, managing TLS (Let's Encrypt)
- A domain name with DNS pointing to the VPS

## Environment variables

| Variable | Default (in image) | Description |
|---|---|---|
| `VIBE_CARLO_DB` | `/data/vibe_carlo.db` | Path to the SQLite database file |
| `VIBE_CARLO_SECURE_COOKIES` | `1` | Set to `1` to mark session cookies as `Secure` (always on in the production image) |

## Building and running

```bash
docker compose up -d --build
```

This builds the image and starts the service. The container joins the `docklinode` network so Caddy can proxy to it directly — no host port mapping is needed.

To stop the service:

```bash
docker compose down
```

The named volume `vibe-carlo-data` persists across restarts and `down`/`up` cycles.

## Creating your first user

```bash
docker compose exec vibe-carlo uv run vibe-carlo-users create user@example.com --password 'your-password'
```

## User management

```bash
# List all users
docker compose exec vibe-carlo uv run vibe-carlo-users list

# Change a password
docker compose exec vibe-carlo uv run vibe-carlo-users change-password user@example.com --password 'new-password'

# Delete a user
docker compose exec vibe-carlo uv run vibe-carlo-users delete user@example.com

# Assign unowned snapshots to a user
docker compose exec vibe-carlo uv run vibe-carlo-users assign-snapshots user@example.com
```

## Caddy configuration

Example Caddyfile snippet (Caddy must also be on the `docklinode` network):

```
your-domain.com {
    reverse_proxy vibe-carlo:8000
}
```

Caddy reaches the container by its name (`vibe-carlo`) over the shared Docker network. TLS certificates are provisioned and renewed automatically via Let's Encrypt.

## Git hook deployment

Example `post-receive` hook (on the VPS bare repo):

```bash
#!/bin/bash
set -e

WORK_DIR=/opt/vibe-carlo

# Check out the latest code
git --work-tree="$WORK_DIR" --git-dir="$(pwd)" checkout -f

cd "$WORK_DIR"

# Rebuild and restart
docker compose up -d --build

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
