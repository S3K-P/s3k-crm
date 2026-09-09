"""Blueprints: a tenant's own process laid over a record's state machine.

A blueprint says which moves through a lifecycle a *particular organization*
allows, and what must be true before each one — required fields, a permission,
a note. It **narrows** the built-in state machine and can never widen it; see
:mod:`.service` for why that direction is the whole design.
"""
