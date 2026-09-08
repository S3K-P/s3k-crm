"""Domain events for the notifications module (ADR-013).

Deliberately empty, and — following ``app.platform.audit.events``'s own
precedent — this file records why rather than pretending otherwise.

The eventual design has every Platform and CRM module publish its domain
events to the transactional outbox, with a notifications handler consuming
the ones worth telling someone about. That does not exist yet (`P4-W26`), so
today's notifications module reaches its data the interim way instead:

* A direct call raises a notification **synchronously, in the caller's own
  transaction** — see ``NotificationService.notify``. If the transaction rolls
  back, so does the claim that the recipient was told.
* A reminder becoming due is **discovered by polling**, not published as an
  event at all — see ``scheduler.py`` and the "why polling" note at the top of
  ``service.py``. There is no writer-side event for "a meeting's reminder time
  has arrived" to publish in the first place; time passing is not an action
  any module performs.

The notifications module publishes no events of its own, and is not expected
to: it is a *consumer* of other modules telling it something happened
(directly, for now), not a producer other modules would consume.
"""
