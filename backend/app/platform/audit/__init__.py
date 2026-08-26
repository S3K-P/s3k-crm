"""Shared Platform module: audit.

The immutable trail of sensitive actions across every product (doc 09 "Audit
Logs", `P1-W08-BE-03`/`BE-07`).

One table, ``platform.audit_logs``, tenant-scoped under the same RLS policy as
every other tenant table and made append-only by a database trigger. One
service, which every other module calls to record an action and which the admin
screen reads through a single permission-gated route.

    models.py      the table, the action vocabulary and the outcome enum
    redaction.py   makes a payload safe to store — secrets out, PII masked
    repository.py  data access; every statement filters on organization_id
    service.py     the module's public interface: record, and read back
    policies.py    who may read the trail, and why nobody may write through it
    schemas.py     the wire contract for the admin screen
    router.py      GET /audit-logs (+ /filters, /{id}); read-only by design
    events.py      why the outbox flow is not what runs today

Writers do not import anything here except :mod:`app.platform.audit.service` —
product modules reach it through ``audit_for_session``.
"""
