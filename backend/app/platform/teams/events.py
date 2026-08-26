"""Domain events for the teams module (ADR-013).

Deliberately empty, and this records why rather than leaving it ambiguous.

A ``platform.team.membership_changed`` event would be the natural way to tell
interested modules that somebody's visibility just widened or narrowed. It
needs the transactional outbox (`P4-W26`), which does not exist, and there is
no consumer for it: visibility is resolved per request from the current rows,
not from a cached projection that would need invalidating.

Until then the module's observable trail is its **audit** records —
``TEAM_CREATED``, ``TEAM_UPDATED``, ``TEAM_DELETED``, ``TEAM_MEMBER_ADDED``,
``TEAM_MEMBER_REMOVED`` and their department equivalents — written
synchronously in the transaction that performs the change. Membership changes
are audited precisely because they alter who can read whose records.
"""
