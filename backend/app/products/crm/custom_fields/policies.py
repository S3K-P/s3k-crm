"""Authorization policies for the custom fields module (ADR-010).

The module's rules are expressible as plain permission checks and are declared
on the routes themselves: ``custom_fields.VIEW`` to read the configuration,
``CREATE``/``EDIT``/``DELETE`` to change it. There is no record-level
dimension — a field definition belongs to the organization, not to a person —
so nothing needs a predicate here.

Note what this module does *not* gate: a record's custom **values**. Those live
in the record and are governed by that record's own module permission and
record-level visibility, which is what stops ``custom_fields.VIEW`` from
becoming a way to read data behind a permission the caller does not hold.
"""
