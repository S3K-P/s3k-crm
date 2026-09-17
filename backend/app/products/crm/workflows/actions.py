"""Executing one workflow action.

**Every action call is a normal call to the entity's own service** —
``LeadService.change_status``, ``TaskService.create_task``,
``EmailService.create_message`` — the same ones a router calls for a human
request. There is no second, automation-only write path: a workflow can
update a field, move a stage, create a task or send a mail only through the
identical validation, blueprint enforcement and tenant scoping a person's own
click would go through (Step 3 / Step 14). The one deliberate difference is
identity — every call below passes ``actor_id=None`` / ``principal=None``,
the same "internal caller with no request behind it" shape
``LeadService.change_status`` and ``OpportunityService.change_stage`` already
document for a background job. Concretely that means:

* Tenant isolation, RLS, required-field and state-machine checks all still
  apply — nothing here reads or writes outside the triggering event's own
  organization.
* A blueprint transition's ``required_fields``/``require_note`` still apply.
* A blueprint transition's ``required_permission`` does **not** apply — there
  is no user to hold it. This is existing, inherited behaviour
  (``BlueprintGuard.check``: "``None`` ... skips only the permission
  requirement, never the field or note ones"), not something Checkpoint 6
  introduces, and it already governs any other system-initiated transition.
  An administrator who wants a permission-gated transition never reachable by
  automation should not build a rule whose ``CHANGE_STAGE``/``CHANGE_STATUS``
  action targets it.

Each function returns a short human-readable string for
``WorkflowRun.action_results`` — never the resolved recipient address or a
record's field values, so a run's history is safe to show to anyone who can
already see the workflow (never a bystander's private data leaking through
"what this automation did").
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.platform.notifications.service import notifications_for_session
from app.platform.organizations.service import organizations_for_session
from app.products.crm.accounts.service import AccountService
from app.products.crm.activities.models import ActivityStatus, ActivityType
from app.products.crm.activities.service import ActivityService
from app.products.crm.campaigns.service import CampaignService
from app.products.crm.common import CrmEntityType, Priority
from app.products.crm.contacts.service import ContactService
from app.products.crm.emails.service import EmailService
from app.products.crm.emails.templates_service import EmailTemplateService
from app.products.crm.emails.templating import render_placeholders
from app.products.crm.emails.variables import resolve_variables
from app.products.crm.leads.models import LeadStatus
from app.products.crm.leads.service import LeadService
from app.products.crm.notes.models import NoteVisibility
from app.products.crm.notes.service import NoteService
from app.products.crm.opportunities.service import OpportunityService
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.tasks.service import TaskService
from app.products.crm.workflows.models import WorkflowActionType, WorkflowEntityType

#: A workflow-authored task/activity/note title or notification body may
#: quote the triggering record — reused from the email module's own
#: substitution rather than a second templating mechanism (Step 8). Not
#: available for a ``TASK``-triggered rule: a task is not a
#: ``CrmEntityType`` and has no variable vocabulary defined for it.
_VARIABLE_ENTITY_TYPES = frozenset(
    {
        WorkflowEntityType.ACCOUNT,
        WorkflowEntityType.CONTACT,
        WorkflowEntityType.LEAD,
        WorkflowEntityType.OPPORTUNITY,
        WorkflowEntityType.CAMPAIGN,
    }
)

#: Fields ``UPDATE_FIELD`` may target, per entity. Deliberately the same set
#: (minus ``custom_fields``) each entity's own ``*Update`` request schema
#: already exposes through PATCH — a status/stage column with a guarded
#: transition (``LeadUpdate.status``, ``OpportunityUpdate.stage_id``) is
#: already absent from that schema and stays absent here, so an automation
#: cannot reach it by any name but ``CHANGE_STATUS``/``CHANGE_STAGE``.
ALLOWED_UPDATE_FIELDS: dict[WorkflowEntityType, frozenset[str]] = {
    WorkflowEntityType.LEAD: frozenset(
        {
            "first_name", "last_name", "company", "email", "phone",
            "lead_source_id", "owner_id", "priority", "expected_deal_size",
            "industry", "website", "company_size", "product_interest", "notes",
            "ai_score",
        }
    ),
    WorkflowEntityType.OPPORTUNITY: frozenset(
        {
            "name", "primary_contact_id", "owner_id", "deal_value", "currency",
            "win_probability", "expected_close_date", "health_score",
            "forecast_category", "competitor", "products", "notes",
        }
    ),
    WorkflowEntityType.ACCOUNT: frozenset(
        {
            "name", "industry", "website", "phone", "company_size",
            "annual_revenue", "status", "owner_id", "primary_contact_id",
            "health_score", "source", "description", "address_line1", "city",
            "state", "postal_code", "country",
        }
    ),
    WorkflowEntityType.CONTACT: frozenset(
        {
            "first_name", "last_name", "account_id", "email", "phone", "mobile",
            "job_title", "department", "owner_id", "status",
            "preferred_communication", "linkedin_url", "notes", "address_line1",
            "city", "state", "postal_code", "country",
        }
    ),
    WorkflowEntityType.CAMPAIGN: frozenset(
        {
            "name", "type", "status", "owner_id", "start_date", "end_date",
            "budget", "expected_revenue", "target_audience", "lead_source_id",
            "products", "notes",
        }
    ),
    WorkflowEntityType.TASK: frozenset({"title", "description", "priority", "due_date"}),
}

#: In-app notification kind for every ``SEND_NOTIFICATION`` action. One
#: kind for all of them, not one per rule — ``Notification.kind`` is a plain
#: ``String`` column, not a database enum (`NotificationKind`'s own docstring:
#: "a new kind must not require an ``ALTER TYPE``"), so this needs no schema
#: change and ``notify()`` itself only asks for ``kind: str``.
WORKFLOW_ALERT_KIND = "WORKFLOW_ALERT"


class WorkflowActionError(AppError):
    """An action's own configuration or preconditions were not satisfiable.

    Distinct from a validation error raised by the underlying service (a
    blueprint refusal, a missing field): this is what a workflow-specific
    problem — an unresolvable recipient, an unknown stage name — raises, so
    ``WorkflowRun.action_results`` can say something more specific than a
    generic exception's ``repr``.
    """

    code = "workflow_action_failed"
    message = "This workflow action could not be completed."


def entity_service_for(
    entity_type: WorkflowEntityType, session: AsyncSession
) -> TenantScopedService[Any]:
    """The service that owns ``entity_type``'s table — the *only* write path.

    Shared with ``.service.handle_record_event``, which uses it to re-read
    the triggering record fresh (never trusting the event payload's
    identifiers for anything but *finding* the row) through the same
    tenant-scoped ``get_or_404`` a human request would use.
    """
    factory = {
        WorkflowEntityType.LEAD: LeadService,
        WorkflowEntityType.OPPORTUNITY: OpportunityService,
        WorkflowEntityType.ACCOUNT: AccountService,
        WorkflowEntityType.CONTACT: ContactService,
        WorkflowEntityType.CAMPAIGN: CampaignService,
        WorkflowEntityType.TASK: TaskService,
    }[entity_type]
    return factory(session)  # type: ignore[return-value]


async def _record_variables(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: WorkflowEntityType,
    record_id: uuid.UUID,
) -> dict[str, str]:
    """``{{record.field}}``-style variables for this record, or none for a task."""
    if entity_type not in _VARIABLE_ENTITY_TYPES:
        return {}
    return await resolve_variables(
        session,
        organization_id=organization_id,
        entity_type=CrmEntityType(entity_type.value),
        entity_id=record_id,
    )


def _render(text: str | None, variables: dict[str, str]) -> str | None:
    if not text:
        return text
    return render_placeholders(text, variables)


async def _resolve_recipient_email(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    recipient: dict[str, Any],
    record: Any,
) -> str:
    """A ``SEND_EMAIL``/``SEND_NOTIFICATION`` action's ``recipient`` config.

    ``{"kind": "OWNER"}`` resolves the record's own ``owner_id``/``assigned_to_id``;
    ``{"kind": "USER", "user_id": ...}`` names someone directly;
    ``{"kind": "STATIC", "address": ...}`` is a literal address (``SEND_EMAIL``
    only — a static address is not a platform user id, so it cannot receive
    an in-app notification).
    """
    kind = recipient.get("kind")
    if kind == "STATIC":
        address = recipient.get("address")
        if not address:
            raise WorkflowActionError("A static recipient address was not configured.")
        return str(address)

    if kind == "USER":
        user_id = recipient.get("user_id")
    else:
        user_id = getattr(record, "owner_id", None) or getattr(record, "assigned_to_id", None)

    if user_id is None:
        raise WorkflowActionError("The recipient could not be resolved to a user.")

    directory = await organizations_for_session(session).member_directory(
        organization_id, [uuid.UUID(str(user_id))]
    )
    identity = directory.get(uuid.UUID(str(user_id)))
    if identity is None:
        raise WorkflowActionError("The resolved recipient is not a member of this organization.")
    return identity.email


async def _resolve_recipient_user_id(
    *, recipient: dict[str, Any], record: Any
) -> uuid.UUID:
    kind = recipient.get("kind")
    user_id = recipient.get("user_id") if kind == "USER" else (
        getattr(record, "owner_id", None) or getattr(record, "assigned_to_id", None)
    )
    if user_id is None:
        raise WorkflowActionError("The recipient could not be resolved to a user.")
    return uuid.UUID(str(user_id))


async def execute_action(
    session: AsyncSession,
    action: dict[str, Any],
    *,
    organization_id: uuid.UUID,
    entity_type: WorkflowEntityType,
    record: Any,
) -> str:
    """Run one configured action against ``record``. Returns a short summary.

    Raises on any failure — including one this function classifies as the
    action's own fault (:class:`WorkflowActionError`) and one bubbling up from
    a service it called (a blueprint refusal, a validation error). The caller
    (`.service._run_rule`) catches either, inside its own per-action
    savepoint, and records it rather than letting one action's failure stop
    the rest of the rule's actions from being attempted.
    """
    action_type = WorkflowActionType(action["type"])
    variables = await _record_variables(
        session, organization_id=organization_id, entity_type=entity_type, record_id=record.id
    )

    if action_type is WorkflowActionType.UPDATE_FIELD:
        return await _update_field(session, action, entity_type=entity_type, record=record)

    if action_type is WorkflowActionType.ASSIGN_OWNER:
        return await _assign_owner(session, action, entity_type=entity_type, record=record)

    if action_type is WorkflowActionType.CREATE_TASK:
        return await _create_task(
            session, action, organization_id=organization_id, entity_type=entity_type,
            record=record, variables=variables,
        )

    if action_type is WorkflowActionType.CREATE_ACTIVITY:
        return await _create_activity(
            session, action, organization_id=organization_id, entity_type=entity_type,
            record=record, variables=variables,
        )

    if action_type is WorkflowActionType.CREATE_NOTE:
        return await _create_note(
            session, action, organization_id=organization_id, entity_type=entity_type,
            record=record, variables=variables,
        )

    if action_type is WorkflowActionType.SEND_EMAIL:
        return await _send_email(
            session, action, organization_id=organization_id, entity_type=entity_type,
            record=record, variables=variables,
        )

    if action_type is WorkflowActionType.SEND_NOTIFICATION:
        return await _send_notification(
            session, action, organization_id=organization_id, record=record, variables=variables
        )

    if action_type is WorkflowActionType.CHANGE_STAGE:
        return await _change_stage(session, action, organization_id=organization_id, record=record)

    if action_type is WorkflowActionType.CHANGE_STATUS:
        return await _change_status(session, action, record=record)

    raise WorkflowActionError(f"Unknown action type '{action_type}'.")


async def _update_field(
    session: AsyncSession, action: dict[str, Any], *, entity_type: WorkflowEntityType, record: Any
) -> str:
    field = action.get("field")
    allowed = ALLOWED_UPDATE_FIELDS.get(entity_type, frozenset())
    if not isinstance(field, str) or field not in allowed:
        raise WorkflowActionError(f"'{field}' is not a field this workflow may update.")
    service = entity_service_for(entity_type, session)
    await service.update(record, actor_id=None, values={field: action.get("value")})
    return f"Set {field}."


async def _assign_owner(
    session: AsyncSession, action: dict[str, Any], *, entity_type: WorkflowEntityType, record: Any
) -> str:
    owner_id = action.get("owner_id")
    if not owner_id:
        raise WorkflowActionError("No owner was configured.")
    field = "assigned_to_id" if entity_type is WorkflowEntityType.TASK else "owner_id"
    service = entity_service_for(entity_type, session)
    await service.update(record, actor_id=None, values={field: uuid.UUID(str(owner_id))})
    return "Reassigned."


async def _create_task(
    session: AsyncSession,
    action: dict[str, Any],
    *,
    organization_id: uuid.UUID,
    entity_type: WorkflowEntityType,
    record: Any,
    variables: dict[str, str],
) -> str:
    if entity_type not in _VARIABLE_ENTITY_TYPES:
        raise WorkflowActionError("CREATE_TASK cannot link to a non-CRM-entity trigger.")
    due_offset = action.get("due_offset_minutes")
    due_date = (
        dt.datetime.now(dt.UTC) + dt.timedelta(minutes=int(due_offset))
        if due_offset is not None
        else None
    )
    recipient = action.get("assignee") or {"kind": "OWNER"}
    assignee_id = await _resolve_recipient_user_id(recipient=recipient, record=record)
    values = {
        "title": _render(action.get("title"), variables) or "Follow up",
        "description": _render(action.get("description"), variables),
        "due_date": due_date,
        "priority": Priority(action["priority"]) if action.get("priority") else Priority.MEDIUM,
        "owner_id": assignee_id,
        "assigned_to_id": assignee_id,
        "related_entity_type": CrmEntityType(entity_type.value),
        "related_entity_id": record.id,
    }
    await TaskService(session).create_task(
        organization_id=organization_id, actor_id=None, values=values
    )
    return "Task created."


async def _create_activity(
    session: AsyncSession,
    action: dict[str, Any],
    *,
    organization_id: uuid.UUID,
    entity_type: WorkflowEntityType,
    record: Any,
    variables: dict[str, str],
) -> str:
    if entity_type not in _VARIABLE_ENTITY_TYPES:
        raise WorkflowActionError("CREATE_ACTIVITY cannot link to a non-CRM-entity trigger.")
    recipient = action.get("owner") or {"kind": "OWNER"}
    owner_id = await _resolve_recipient_user_id(recipient=recipient, record=record)
    due_offset = action.get("due_offset_minutes")
    due_date = (
        dt.datetime.now(dt.UTC) + dt.timedelta(minutes=int(due_offset))
        if due_offset is not None
        else None
    )
    values = {
        "type": ActivityType(action.get("activity_type", ActivityType.TASK.value)),
        "subject": _render(action.get("subject"), variables) or "Automated follow-up",
        "description": _render(action.get("description"), variables),
        "status": ActivityStatus.PLANNED,
        "due_date": due_date,
        "owner_id": owner_id,
        "related_entity_type": CrmEntityType(entity_type.value),
        "related_entity_id": record.id,
    }
    await ActivityService(session).create_activity(
        organization_id=organization_id, actor_id=None, values=values
    )
    return "Activity created."


async def _create_note(
    session: AsyncSession,
    action: dict[str, Any],
    *,
    organization_id: uuid.UUID,
    entity_type: WorkflowEntityType,
    record: Any,
    variables: dict[str, str],
) -> str:
    if entity_type not in _VARIABLE_ENTITY_TYPES:
        raise WorkflowActionError("CREATE_NOTE cannot link to a non-CRM-entity trigger.")
    content = _render(action.get("body"), variables)
    if not content:
        raise WorkflowActionError("No note body was configured.")
    values = {
        "content": content,
        "visibility": NoteVisibility(action.get("visibility", NoteVisibility.ORGANIZATION.value)),
        "related_entity_type": CrmEntityType(entity_type.value),
        "related_entity_id": record.id,
    }
    await NoteService(session).create_note(
        organization_id=organization_id, actor_id=None, values=values
    )
    return "Note added."


async def _send_email(
    session: AsyncSession,
    action: dict[str, Any],
    *,
    organization_id: uuid.UUID,
    entity_type: WorkflowEntityType,
    record: Any,
    variables: dict[str, str],
) -> str:
    recipient = action.get("recipient") or {"kind": "OWNER"}
    to_address = await _resolve_recipient_email(
        session, organization_id=organization_id, recipient=recipient, record=record
    )
    emails = EmailService(session, settings=get_settings())
    sender_address, sender_name = await emails.sender_identity(organization_id, None)

    template_id = action.get("template_id")
    if template_id:
        has_crm_record = entity_type in _VARIABLE_ENTITY_TYPES
        template = await EmailTemplateService(session).get_or_404(
            uuid.UUID(str(template_id)), organization_id
        )
        rendered = await emails.render_template(
            template,
            organization_id=organization_id,
            entity_type=CrmEntityType(entity_type.value) if has_crm_record else None,
            entity_id=record.id if has_crm_record else None,
            sender_name=sender_name,
            sender_email=sender_address,
            organization_name=None,
        )
        subject = rendered["subject"]
        body_text = rendered["body_text"]
        body_html = rendered.get("body_html")
    else:
        subject = _render(action.get("subject"), variables) or "Update"
        body_text = _render(action.get("body_text"), variables) or ""
        body_html = None

    values: dict[str, Any] = {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "to_addresses": [to_address],
        "send": True,
    }
    if entity_type in _VARIABLE_ENTITY_TYPES:
        values["related_entity_type"] = CrmEntityType(entity_type.value)
        values["related_entity_id"] = record.id
    await emails.create_message(
        organization_id=organization_id,
        actor_id=None,
        sender_address=sender_address,
        sender_name=sender_name,
        values=values,
    )
    return "Email queued."


async def _send_notification(
    session: AsyncSession,
    action: dict[str, Any],
    *,
    organization_id: uuid.UUID,
    record: Any,
    variables: dict[str, str],
) -> str:
    recipient = action.get("recipient") or {"kind": "OWNER"}
    recipient_id = await _resolve_recipient_user_id(recipient=recipient, record=record)
    title = _render(action.get("title"), variables) or "Workflow alert"
    body = _render(action.get("body"), variables)
    await notifications_for_session(session).notify(
        organization_id=organization_id,
        recipient_user_id=recipient_id,
        kind=WORKFLOW_ALERT_KIND,
        title=title,
        body=body,
        entity_type=None,
        entity_id=None,
    )
    return "Notification sent."


async def _change_stage(
    session: AsyncSession, action: dict[str, Any], *, organization_id: uuid.UUID, record: Any
) -> str:
    stage_name = action.get("stage_name")
    if not stage_name:
        raise WorkflowActionError("No target stage was configured.")
    service = OpportunityService(session)
    stages = await service.list_stages(organization_id)
    target = str(stage_name).strip().lower()
    match = next((s for s in stages if s.name.strip().lower() == target), None)
    if match is None:
        raise WorkflowActionError(f"Stage '{stage_name}' does not exist in this pipeline.")
    await service.change_stage(record, stage_id=match.id, actor_id=None, principal=None)
    return f"Moved to {match.name}."


async def _change_status(session: AsyncSession, action: dict[str, Any], *, record: Any) -> str:
    status_value = action.get("status")
    if not status_value:
        raise WorkflowActionError("No target status was configured.")
    try:
        new_status = LeadStatus(status_value)
    except ValueError as exc:
        raise WorkflowActionError(f"'{status_value}' is not a valid lead status.") from exc
    await LeadService(session).change_status(
        record, new_status=new_status, actor_id=None, principal=None
    )
    return f"Status set to {new_status.value}."


__all__ = [
    "ALLOWED_UPDATE_FIELDS",
    "WORKFLOW_ALERT_KIND",
    "WorkflowActionError",
    "entity_service_for",
    "execute_action",
]
