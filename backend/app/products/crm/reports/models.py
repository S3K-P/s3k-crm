"""SQLAlchemy models for the reports module.

Deliberately empty, and this file records why rather than leaving a
scaffolding docstring that stopped being true.

The built-in reports are **code, not rows**: ``catalog.py`` is the catalogue,
the same way ``imports/catalog.py`` is the catalogue of importable entities.
Seeding nine rows into every organization to describe queries that live in
this repository would create a second source of truth, one a migration would
then have to keep in step with the code on every edit.

Tables arrive when reports gain state a tenant owns rather than shares: a
*saved* report — one of these definitions plus a name, a folder and a
remembered period — and the folders to file them in. That is deferred
deliberately, to be built once there is a screen asking for it, and nothing
in the current shape has to change to accommodate it.
"""
