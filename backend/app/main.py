"""ASGI entrypoint.

    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Configuration is validated here, so a missing or invalid setting aborts the
process immediately with an actionable message.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.application import create_app
from app.core.config import load_settings_or_exit

app: FastAPI = create_app(load_settings_or_exit())
