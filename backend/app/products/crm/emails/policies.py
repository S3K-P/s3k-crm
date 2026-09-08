"""Authorization policies for the emails module (ADR-010).

Two rules live here rather than in the generic service, because neither is
expressible as a permission code.

**A draft belongs to its author.** An unsent message is somebody's work in
progress, not the record's history. It is excluded from every other reader's
queries — in SQL, so it is neither fetched nor counted — and joins the shared
timeline only when it is sent. The same reasoning notes use for ``PRIVATE``,
and the same mechanism.

**BCC is visible only to the sender.** The entire meaning of a blind copy is
that the other recipients cannot see it, and a colleague reading the account
timeline is some other recipient's colleague too. Holders of ``VIEW_ALL`` do
see it, because somebody has to be able to answer "who was copied on this"
during a dispute; that grant is what already means "read what colleagues did",
and Manager and Admin hold it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, or_

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.emails.models import EmailMessage, EmailStatus

#: The permission module these routes are gated on.
MODULE = "emails"


def readable_messages(viewer_id: uuid.UUID | None) -> ColumnElement[bool]:
    """Restrict a query to messages ``viewer_id`` may read.

    Anything that has left the building is part of the record's history and is
    readable by anyone who can read the record. A draft is readable only by the
    person writing it.

    ``viewer_id`` is ``None`` for an unauthenticated internal caller — the
    worker, in practice — which resolves to "sent messages only". That is the
    safe direction: the worker loads the message it is delivering by id
    through a different path, and nothing else internal has business reading
    somebody's drafts.
    """
    sent = EmailMessage.status != EmailStatus.DRAFT
    if viewer_id is None:
        return sent
    own_draft = EmailMessage.created_by_id == viewer_id
    return or_(sent, own_draft)


def may_see_blind_copies(principal: Principal, message: EmailMessage) -> bool:
    """Whether ``principal`` may be shown ``message``'s BCC list.

    The sender always may — they chose it. Anyone else needs ``VIEW_ALL`` on
    this module.
    """
    if message.created_by_id is not None and message.created_by_id == principal.user_id:
        return True
    return principal.has_permission(MODULE, PermissionAction.VIEW_ALL)


def may_read_template(
    *, is_shared: bool, owner_id: uuid.UUID | None, viewer_id: uuid.UUID | None
) -> bool:
    """Whether a template is visible to ``viewer_id``.

    Shared templates are the organization's; a private one is its author's
    working draft. The list query applies the same rule in SQL — this is the
    single-row form, used after a fetch by id.
    """
    if is_shared:
        return True
    return owner_id is not None and owner_id == viewer_id


__all__ = [
    "MODULE",
    "may_read_template",
    "may_see_blind_copies",
    "readable_messages",
]
