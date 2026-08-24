"""Shared Platform module: documents.

Attachment metadata in PostgreSQL, the files themselves in S3-compatible object
storage — Cloudflare R2 in deployed environments, MinIO locally (ADR-014,
`P2-W19-BE-02`/`BE-03`/`BE-04`).

**Bytes never pass through this application.** The browser is handed a
pre-signed URL and PUTs the file straight to storage, then asks the API to
confirm; downloads work the same way in reverse (doc 09 "Documents & File
Storage", doc 13 "File Upload Security"). The API authorizes and records; it is
not in the data path.

    models.py      the ``platform.attachments`` table — metadata only
    storage.py     the boto3 S3 adapter: pre-sign, head, delete
    validation.py  MIME whitelist, size ceiling, filename and key safety
    repository.py  data access; every statement filters on organization_id
    service.py     upload / confirm / download / delete, and their failure paths
    policies.py    the two independent gates, and why both are needed
    schemas.py     the wire contract
    router.py      /api/v1/attachments — and the product-access inversion
    events.py      why the outbox flow is not what runs today

Files hang off a CRM record through a loose ``entity_type``/``entity_id`` pair
rather than a foreign key, because several products will want attachments and
Platform must not know any of their tables. Whether a caller may reach the
linked record is therefore a question this module cannot answer itself: it
declares a Protocol, the product implements it, and the composition root wires
them together. See ``policies.py`` and ``router.py``.
"""
