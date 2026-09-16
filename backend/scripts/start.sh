#!/bin/sh
# ---------------------------------------------------------------------------
# Container entrypoint for platform deployments (Railway, and anything else
# that assigns a port at run time).
#
# Two things separate this from the plain `uvicorn` command used locally:
#
#   $PORT      the platform picks the port and routes to it. Binding a fixed
#              8000 makes the health check fail and the deployment roll back.
#   migrations the schema has to exist before the first request.
#
# On migrations and replicas (Phase C): this used to be safe only because
# `numReplicas` was 1, and the note here said to move it to a pre-deploy
# command before scaling. That is no longer necessary — `migrations/env.py`
# takes a transaction-scoped advisory lock, so replicas booting together
# serialize: the first migrates, the rest wait, find the schema at head and
# continue. The other reason for the pin, an in-process reminder poller, moved
# to the worker service (`scripts/worker.sh`).
#
# Both `alembic` and `uvicorn` come from the image's virtualenv, which the
# Dockerfile puts on PATH.
# ---------------------------------------------------------------------------
set -eu

. "$(dirname "$0")/require-public-app-url.sh"

PORT="${PORT:-8000}"

echo "entrypoint: applying database migrations"
alembic upgrade head

echo "entrypoint: starting uvicorn on 0.0.0.0:${PORT}"
# --proxy-headers with a trusting --forwarded-allow-ips is correct here and
# only here: the container is reachable exclusively through the platform's own
# edge proxy, so X-Forwarded-* always arrives from it. Without them the app
# believes every request is plain http, which breaks scheme-aware redirects
# and the Secure refresh cookie.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --proxy-headers \
    --forwarded-allow-ips='*'
