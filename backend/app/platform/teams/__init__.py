"""Shared Platform module: teams.

Departments, teams and their membership (doc 04 "Team & Department", doc 08 —
Platform owns organizational structure).

    models.py      platform.departments / teams / team_memberships
    repository.py  data access; every statement filters on organization_id
    service.py     use cases, and the team-peer read products consume
    policies.py    the permission this module is gated on
    schemas.py     the wire contract
    router.py      /api/v1/teams and /api/v1/departments
    events.py      why the outbox flow is not what runs today

**Why this closes B02.** Record-level visibility shipped as *owner vs
organization-wide* only, because CR07 found nothing for a team predicate to
resolve against. This module supplies it: :meth:`TeamService.peer_user_ids`
answers "whose records may this user also see", and the CRM's
``RecordVisibility`` composes that answer into the same SQL predicate it
already applies. Products consume it through the service, never by querying
these tables (ARCHITECTURE-BOUNDARIES.md rule 2).
"""
