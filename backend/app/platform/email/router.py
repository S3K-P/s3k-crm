"""HTTP routes for the email delivery log — read-only, like the audit trail.

Two endpoints and no writes. Sending is something the product does on its own
behalf when a record changes; there is no "send this" API to expose, and a
resend button would need its own permission and its own rate limit before it
could exist safely.

**Gated on ``audit.VIEW``, deliberately reusing that module rather than
inventing one.** The question this screen answers — "what did the system do,
and did it work?" — is the audit question, the readers are the same people, and
the sensitivity is the same order: the trail already names who signed in and
whose account was locked, so it is not widened by also naming who was sent an
invitation. A new permission module would need a migration, a role-template
decision and an entry in the frontend's permission matrix, all to gate one
read-only screen to exactly the audience ``audit.VIEW`` already describes.

The organization is never a parameter. It comes from the verified tenant
context, the repository filters on it explicitly, and RLS filters again — which
matters here because this table's policy is NULL-aware and an unscoped read
would return the untenanted rows rather than none.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.core.pagination import Page, PageParams, page_params
from app.platform.audit.policies import MODULE as AUDIT_MODULE
from app.platform.audit.policies import VIEW
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.email.models import EmailDeliveryStatus
from app.platform.email.repository import EmailDeliveryRepository
from app.platform.email.schemas import (
    EmailDeliveryResponse,
    EmailDeliverySummaryResponse,
)

router = APIRouter()

PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_repository(session: DbSession) -> EmailDeliveryRepository:
    return EmailDeliveryRepository(session)


RepositoryDep = Annotated[EmailDeliveryRepository, Depends(get_repository)]

#: Declared once so no route here can be added with a weaker gate by accident.
DeliveryReader = Annotated[Principal, Depends(require_permission(AUDIT_MODULE, VIEW))]


@router.get("", response_model=Page[EmailDeliveryResponse])
async def list_deliveries(
    principal: DeliveryReader,
    repository: RepositoryDep,
    params: PageParamsDep,
    delivery_status: Annotated[
        EmailDeliveryStatus | None,
        Query(alias="status", description="Only deliveries in this state."),
    ] = None,
    template: Annotated[
        str | None, Query(max_length=80, description="Exact template name.")
    ] = None,
    to_address: Annotated[
        str | None,
        Query(max_length=320, description="Substring of the recipient address."),
    ] = None,
    sent_from: Annotated[
        dt.datetime | None, Query(description="Requested at or after (ISO 8601).")
    ] = None,
    sent_to: Annotated[
        dt.datetime | None, Query(description="Requested at or before (ISO 8601).")
    ] = None,
) -> Page[EmailDeliveryResponse]:
    """This organization's outbound mail, newest first.

    Sorting accepts ``created_at``, ``sent_at``, ``status``, ``template`` and
    ``to_address``; anything else falls back to ``created_at``.
    """
    rows, total = await repository.list_deliveries(
        principal.organization_id,
        params=params,
        status=delivery_status,
        template=template,
        to_address=to_address,
        sent_from=sent_from,
        sent_to=sent_to,
    )
    return Page.build(
        [EmailDeliveryResponse.model_validate(row) for row in rows],
        total=total,
        params=params,
    )


@router.get("/summary", response_model=EmailDeliverySummaryResponse)
async def get_summary(
    principal: DeliveryReader,
    repository: RepositoryDep,
    since: Annotated[
        dt.datetime | None,
        Query(description="Count only deliveries requested at or after this."),
    ] = None,
) -> EmailDeliverySummaryResponse:
    """Counts by state, and the templates this organization has actually sent."""
    counts = await repository.counts_by_status(principal.organization_id, since=since)
    templates = await repository.distinct_templates(principal.organization_id)
    return EmailDeliverySummaryResponse(
        counts={status.value: count for status, count in counts.items()},
        templates=list(templates),
    )


__all__ = ["router"]
