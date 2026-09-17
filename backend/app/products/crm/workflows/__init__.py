"""Workflow automation (Checkpoint 6): trigger -> conditions -> actions.

A tenant-configured rule that watches for something happening to a CRM
record or a task — created, updated, a field changing, a stage or status
move, an owner reassignment, or a due date arriving — and, when its
conditions hold, runs one or more actions through the same validated
services a human user's request would: updating a field, assigning an
owner, creating a task or note, sending an email or in-app notification, or
moving a lead's status / an opportunity's stage through the existing
blueprint-guarded transition.

Built entirely on infrastructure earlier checkpoints already shipped:

* **Trigger delivery** is the transactional outbox (`app.platform.events`,
  ADR-013) — a record write enqueues an identifiers-only event in the same
  transaction as the change, and the ARQ worker drains it exactly like every
  other outbox event.
* **Condition evaluation** reuses
  :mod:`app.products.crm.layouts.evaluate` — the same pure, DB-free operator
  vocabulary a Checkpoint 4 conditional-field rule already evaluates a
  record against.
* **Actions** call the entity's own service (`LeadService.change_status`,
  `TaskService.create_task`, `EmailService.create_message`, ...), never a
  parallel write path — so a workflow can no more bypass a blueprint,
  required-field check or tenant boundary than a person clicking a button
  could.

See :mod:`app.products.crm.workflows.service` for the engine and
:mod:`app.products.crm.workflows.context` for how a chain of
workflow-triggered writes is depth-limited and correlated.
"""
