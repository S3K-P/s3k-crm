"""CSV import for the CRM entities that receive bulk data (`P3-W23-BE-01/03`).

Three entities are importable — leads, accounts and contacts — because those
are the three a customer arrives with a spreadsheet of. Opportunities are
deliberately absent: a deal without a pipeline stage and an account is not a
deal, and inventing either during an import produces plausible-looking
rubbish in the forecast.

**Nothing here re-implements a rule.** Rows are validated by the entity's own
``*Create`` schema and written by the entity's own service, so import
validation is API validation, import duplicate handling is the duplicate
handling the API already documents (decision C03), and every imported record
is audited by the same code that audits one created through the UI.

**The dry run is the real thing, rolled back.** ``preview`` executes the whole
import inside a SAVEPOINT and discards it. That is more expensive than
re-deriving what *would* have happened, and it is the only way the preview
cannot lie: there is no second implementation to drift from the committing one.

Synchronous, with a hard row cap (:data:`MAX_IMPORT_ROWS`). The batch worker
that would lift it is `P3-W23-BE-02`, formally out of scope for this round —
so the limit is enforced and stated rather than left to a timeout.
"""

from __future__ import annotations

from app.products.crm.imports.catalog import IMPORTABLE, ImportableEntity
from app.products.crm.imports.service import MAX_IMPORT_ROWS, ImportService

__all__ = ["IMPORTABLE", "MAX_IMPORT_ROWS", "ImportService", "ImportableEntity"]
