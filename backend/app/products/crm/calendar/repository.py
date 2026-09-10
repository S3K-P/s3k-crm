"""No queries of its own.

The calendar reads through the activities and tasks *services*, not through
their tables: ARCHITECTURE-BOUNDARIES.md rule 6 says a module owns its tables
and cross-module reads go through the owning service, and the record-level
visibility rules those services apply are exactly what must not be
re-implemented here. See :mod:`.service`.
"""
