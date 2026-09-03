#!/bin/sh
# ---------------------------------------------------------------------------
# Container entrypoint for platform deployments (Railway, and anything else
# that assigns a port at run time).
#
# Two things separate this from the plain `uvicorn` command used locally:
#
#   $PORT      the platform picks the port and routes to it. Binding a fixed
#              8000 makes the health check fail and the deployment roll back.
#   migrations the schema has to exist before the first request. One replica
#              runs here, so `alembic upgrade head` on boot is safe; if this
#              service is ever scaled past one, move it to Railway's
#              pre-deploy command so replicas cannot race each other.
#
# Both `alembic` and `uvicorn` come from the image's virtualenv, which the
# Dockerfile puts on PATH.
# ---------------------------------------------------------------------------
set -eu

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
