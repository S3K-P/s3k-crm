"""Domain events for the audit module (ADR-013).

Deliberately empty, and this file records why rather than pretending otherwise.

The eventual design (doc 11 "Audit Event Flow", `P4-W27-BE-02`) has every
Platform and CRM module publish its domain events to the transactional outbox,
with an audit handler consuming them and appending the trail. That inverts
today's arrangement: modules would stop calling the audit service directly and
the trail would be derived from events instead.

Until the outbox exists (`P4-W26`), the audit trail is written **synchronously,
in the transaction that performs the audited action** — see
:mod:`app.platform.audit.service`. That is not a placeholder for the event
flow so much as a stricter version of it: a record written in the same
transaction cannot describe a change that was rolled back, and cannot be lost
because a queue was unavailable.

The audit module publishes no events of its own and is not expected to. An
audit record is the terminal observation of something that already happened;
emitting an event about having recorded one would only invite a loop.
"""
