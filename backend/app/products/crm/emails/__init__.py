"""S3K CRM module: emails.

User-authored mail, sent from the CRM against a customer record.

This is the *composition* half of email, and the platform module beside it
(``app.platform.email``) is the *transport* half. The split matters:

* ``app.platform.email`` owns the provider, the delivery log and the three
  system messages the product sends on its own behalf — an invitation, a
  password reset, a meeting reminder. Those have no author; the product sends
  them because something happened.
* This module owns mail a person wrote: a body they typed, recipients they
  chose, a template they saved, a thread it belongs to and the record it is
  filed against. Every message here has an author, and that author is
  accountable for it.

Both send through the same provider and the same outbox, which is the point —
there is one way out of this system, one retry policy and one delivery log,
whether the sender is a person or the product.

Nothing is re-exported here, deliberately. Every other CRM package leaves its
``__init__`` as a docstring so that ``from app.products.crm.<module> import
router`` resolves to the *submodule*, which is how the composition root mounts
them; binding a name called ``router`` here would shadow that module with the
``APIRouter`` object inside it and break the import for this module alone.
"""
