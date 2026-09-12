#!/usr/bin/env bash
# Run the JS-parity tests without Node installed locally, using Docker.
#
# Pulls the Node image once up front (the tests impose a 30s per-call timeout,
# which a cold pull would blow), then runs pytest with `node` pointed at the
# containerised wrapper.
#
# Usage:
#   scripts/run-js-tests.sh                 # the parity suite
#   scripts/run-js-tests.sh -k bootstrap    # extra args go to pytest
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${VIBE_CARLO_NODE_IMAGE:-node:22-alpine}"

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Pulling $IMAGE (one time)..."
    docker pull "$IMAGE"
fi

export VIBE_CARLO_NODE="$REPO_ROOT/scripts/node-docker"

exec uv run --directory "$REPO_ROOT" pytest \
    "$REPO_ROOT/tests/test_client_sim_parity.py" "$@"
