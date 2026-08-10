"""Shared Platform module: organizations.

Tenants and memberships. The organization is the tenant boundary for every product (ADR-007).

Scaffolded in Phase 0 (P0-W01-BE-03). No behaviour is implemented yet — the
modules below are placeholders that fix the shape every business module takes:

    router.py      FastAPI routes; HTTP concerns only
    service.py     use cases and business rules; the module's public interface
    repository.py  data access; the only layer that touches the ORM
    schemas.py     Pydantic v2 request/response models
    models.py      SQLAlchemy 2.0 ORM models
    policies.py    authorization predicates (ADR-010)
    events.py      domain events published via the outbox (ADR-013)
"""
