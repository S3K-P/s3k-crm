#!/bin/sh
# ---------------------------------------------------------------------------
# Container entrypoint for the background worker (ADR-013, Phase C).
#
# Deployed as a **second service from the same image** as the API, with the
# same environment. It drains the transactional outbox and dispatches due
# reminders; see `app/worker.py` for what each job does and why both are safe
# to run in several copies.
#
# Three differences from `start.sh`, all deliberate:
#
#   no migrations  the API service runs them on boot and this would race it.
#                  A worker that starts before the schema is ready finds no
#                  outbox table, logs, and succeeds on its next tick.
#   no port        it serves nothing. Do not give this service a health check
#                  path — there is no HTTP listener to answer it.
#   no --reload    same as the API in production, stated because the local
#                  developer command does use it.
#
# `arq` comes from the image's virtualenv, which the Dockerfile puts on PATH.
# ---------------------------------------------------------------------------
set -eu

echo "entrypoint: starting the outbox worker"
exec arq app.worker.WorkerSettings
