"""Authorization for the reports module (ADR-010).

**There is no ``reports`` permission module, and its absence is the design.**
Reading a report is reading the records it aggregates: a pipeline report is a
grouped read of opportunities, and a lead funnel is a grouped read of leads.
Each entry in ``catalog.py`` therefore names the module it draws from, and
both routes authorize against *that* — ``<module>.VIEW`` — rather than
against a permission of their own.

This is the call ``imports/catalog.py`` already makes in the other direction:
import requires ``<module>.CREATE`` because importing is creating, and
inventing an ``IMPORT`` action "would mean a migration and a role change for
every existing tenant, to express a grant that ``CREATE`` already covers".
The same sentence holds here with ``VIEW``, and it buys precision as well as
economy — a rep who cannot see opportunities cannot open the pipeline report,
with no second permission to keep in step.

**Row-level narrowing is not optional and not separate.** The same
``RecordVisibility`` the module's list endpoint applies is resolved for the
report and pushed into the aggregate. Authorizing the route and then
aggregating over everything would leak the shape of data the caller cannot
open — a total is a disclosure even when every underlying row stays hidden.

There is consequently nothing to gate at the route level, which is why
``router.py`` takes ``PermissionedPrincipal`` and the service makes the
decision. See that module's docstring for why that is safe here and would not
be in a handler that failed to make it.
"""

from __future__ import annotations

from typing import Final

from app.platform.authorization.service import Action

#: The action every report requires on its own declared module.
VIEW: Final = Action.VIEW

__all__ = ["VIEW"]
