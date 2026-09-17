"""The system email templates added for verification and notifications."""

from __future__ import annotations

import uuid

import pytest

from app.platform.email.templates import EMAIL_VERIFICATION, NOTIFICATION, render
from app.products.crm.shared.record_notifications import (
    RECORD_NOTIFICATION_KINDS,
    notify_record_event,
)


def test_the_verification_email_carries_its_link_and_expiry() -> None:
    rendered = render(
        EMAIL_VERIFICATION,
        {
            "verify_url": "https://app.example/verify-email?token=abc",
            "expires_on": "18 September 2026 at 10:00 UTC",
        },
    )

    assert "https://app.example/verify-email?token=abc" in rendered.text_body
    assert "18 September 2026" in rendered.text_body
    assert rendered.subject == "Confirm your email address for S3K"


def test_the_verification_email_refuses_to_render_without_a_link() -> None:
    with pytest.raises(KeyError, match="verify_url"):
        render(EMAIL_VERIFICATION, {"expires_on": "tomorrow"})


def test_the_notification_email_uses_the_notifications_own_text() -> None:
    rendered = render(
        NOTIFICATION,
        {
            "recipient_name": "Asha",
            "title": "Task assigned to you: Call {braces} back",
            "message": 'You have been assigned the task "Call back".',
            "record_url": "https://app.example/tasks",
        },
    )

    # Values containing braces are substituted, never re-interpreted.
    assert rendered.subject == "Task assigned to you: Call {braces} back"
    assert rendered.text_body.startswith("Hello Asha,")
    assert "https://app.example/tasks" in rendered.text_body


def test_the_notification_email_needs_a_recipient_and_a_link() -> None:
    with pytest.raises(KeyError, match="record_url"):
        render(NOTIFICATION, {"recipient_name": "A", "title": "T", "message": "M"})


def test_only_the_roadmap_notification_kinds_exist() -> None:
    assert frozenset(
        {"TASK_ASSIGNED", "TASK_COMPLETED", "LEAD_QUALIFIED", "OPPORTUNITY_WON"}
    ) == RECORD_NOTIFICATION_KINDS
    # Notification.kind is String(32).
    assert all(len(kind) <= 32 for kind in RECORD_NOTIFICATION_KINDS)


async def _notify(**overrides: object) -> bool:
    values: dict[str, object] = {
        "organization_id": uuid.uuid4(),
        "recipient_id": uuid.uuid4(),
        "actor_id": uuid.uuid4(),
        "kind": "TASK_ASSIGNED",
        "title": "t",
        "message": "m",
        "entity_type": "task",
        "entity_id": uuid.uuid4(),
        "record_path": "/tasks",
    }
    values.update(overrides)
    # No session is needed on the paths under test: each returns before
    # touching the database.
    return await notify_record_event(None, **values)  # type: ignore[arg-type]


async def test_nobody_is_notified_of_their_own_action() -> None:
    same = uuid.uuid4()
    assert await _notify(recipient_id=same, actor_id=same) is False


async def test_a_record_without_a_recipient_notifies_nobody() -> None:
    assert await _notify(recipient_id=None) is False


async def test_an_invented_notification_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown CRM notification kind"):
        await _notify(kind="RECORD_VIEWED")
