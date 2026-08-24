"""Domain events for the documents module (ADR-013).

Deliberately empty, and this records why rather than leaving it ambiguous.

Doc 11 lists ``platform.document.uploaded`` as an event the search indexer will
consume. That needs the transactional outbox (`P4-W26`), which does not exist,
and there is no search indexer to consume it (`P3-W20`). Publishing to nothing
would be ceremony.

Until then the module's observable trail is its **audit** records —
``ATTACHMENT_UPLOADED``, ``ATTACHMENT_DOWNLOADED``, ``ATTACHMENT_DELETED`` —
written synchronously in the transaction that performs the action, so they
cannot describe an upload that was rolled back. See
:mod:`app.platform.audit.service`.
"""
