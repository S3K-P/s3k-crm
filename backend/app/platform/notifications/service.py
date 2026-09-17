"""Use cases for the notifications module.

This module is the notifications module's public interface: other modules
call the service layer here and never reach into its repository or models.

Email is the first implemented use case: every outgoing CRM email goes
through Microsoft Graph via :func:`send_email` — the only supported email
transport. See ``email_service.py`` for the Graph transport itself
(authentication, request shape, error handling).

In-app and SMS notification delivery remain unimplemented placeholders.
"""

from __future__ import annotations

from app.platform.notifications.email_service import (
    EmailAttachment,
    EmailDeliveryError,
    EmailMessage,
    EmailNotConfiguredError,
    GraphEmailService,
    create_email_service,
    send_email,
)

__all__ = [
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailMessage",
    "EmailNotConfiguredError",
    "GraphEmailService",
    "create_email_service",
    "send_email",
]
