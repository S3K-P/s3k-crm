"""No tables.

The calendar owns no storage: an entry is a projection of a ``crm.meetings``
row or a ``crm.tasks`` row, both of which belong to other modules and keep
their own lifecycle, permissions and audit trail. See :mod:`.schemas` for the
projected shape and :mod:`.service` for the rule that a projection is never
written through.

This file exists so the module keeps the seven-file shape every other module
has (ARCHITECTURE-BOUNDARIES.md), and so the absence of a table is a stated
decision rather than something a reader has to infer.
"""
