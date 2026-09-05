"""Running a report — the module's public interface.

Four things happen here, in this order, and the order is the security model:

1. **The definition is resolved**, or the caller gets a 404. An unknown key
   never reaches a query.
2. **The caller is authorized against that report's own module.** Not against
   a ``reports`` permission — see ``catalog.py`` for why there isn't one.
3. **Record-level visibility is resolved for the same module** and handed to
   the query, which applies it inside the aggregate rather than to the result.
4. **User ids are resolved to names** through the Platform service, and only
   then does anything leave this layer.

Step 3 is the one worth restating. An aggregate over rows the caller cannot
open is a disclosure that no later check can undo: a total tells you the
total. The predicate therefore travels into the SQL, and the number a rep
sees is computed from the rep's own rows.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import PermissionDeniedError
from app.platform.organizations.service import organizations_for_session
from app.products.crm.reports.catalog import (
    REPORTS,
    ReportContext,
    ReportDefinition,
    person_columns,
)
from app.products.crm.reports.policies import VIEW
from app.products.crm.reports.repository import MAX_REPORT_ROWS, ReportRepository
from app.products.crm.reports.schemas import (
    ChartInfo,
    ReportColumnInfo,
    ReportResult,
    ReportSummary,
)
from app.products.crm.shared.visibility import RecordVisibility

#: Shown in place of a name for an owner id that resolves to nobody — a user
#: removed from the organization, or a record whose owner was never set. The
#: rows still count towards the report; hiding them would make the totals
#: disagree with the list they summarise.
UNASSIGNED = "Unassigned"


class ReportService:
    """The catalogue, and the one call that runs an entry in it."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = ReportRepository(session)
        self._organizations = organizations_for_session(session)

    # --- Catalogue ---------------------------------------------------------

    @staticmethod
    def catalogue(principal: Principal) -> list[ReportSummary]:
        """Reports this caller may actually run.

        Filtered by the permission snapshot rather than listed in full and
        refused on run: a catalogue that advertises a report the caller cannot
        open is a menu of locked doors. A caller holding no CRM ``VIEW`` at
        all sees an empty list, which is not an error — the same call
        ``search`` makes for the same situation.
        """
        return [
            ReportSummary(
                key=definition.key,
                name=definition.name,
                description=definition.description,
                category=definition.category,
                module=definition.module,
                accepts_date_range=definition.accepts_date_range,
                chart=_chart_info(definition),
            )
            for definition in REPORTS.values()
            if principal.has_permission(definition.module, VIEW)
        ]

    # --- Running -----------------------------------------------------------

    async def run(
        self,
        key: str,
        principal: Principal,
        *,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        today: dt.date | None = None,
    ) -> ReportResult:
        """Authorize, scope, execute and shape one report.

        Raises:
            NotFoundError: no report with that key.
            PermissionDeniedError: the caller lacks ``VIEW`` on the module the
                report reads.
        """
        definition = REPORTS.get(key)
        if definition is None:
            raise NotFoundError("Report not found.")

        if not principal.has_permission(definition.module, VIEW):
            raise PermissionDeniedError

        # Resolved from the same snapshot the check above read, so the two
        # cannot disagree — the pattern `require_permission` establishes for
        # every list endpoint.
        visibility = RecordVisibility.for_module(principal, definition.module)

        window_from = date_from if definition.accepts_date_range else None
        window_to = date_to if definition.accepts_date_range else None

        rows = await definition.run(
            self._repository,
            ReportContext(
                organization_id=principal.organization_id,
                visibility=visibility,
                date_from=window_from,
                date_to=window_to,
                today=today or dt.datetime.now(dt.UTC).date(),
            ),
        )

        truncated = len(rows) > MAX_REPORT_ROWS
        if truncated:
            rows = rows[:MAX_REPORT_ROWS]

        await self._resolve_people(definition, rows, principal)

        return ReportResult(
            key=definition.key,
            name=definition.name,
            description=definition.description,
            category=definition.category,
            generated_at=dt.datetime.now(dt.UTC),
            columns=[
                ReportColumnInfo(key=column.key, label=column.label, type=column.type.value)
                for column in definition.columns
            ],
            rows=rows,
            totals=_totals(definition, rows),
            chart=_chart_info(definition),
            date_from=window_from,
            date_to=window_to,
            row_limit_reached=truncated,
        )

    async def _resolve_people(
        self,
        definition: ReportDefinition,
        rows: list[dict[str, Any]],
        principal: Principal,
    ) -> None:
        """Replace user ids with display names, in place.

        One directory read for the whole report, through the Platform service
        — a product may not query ``platform.users`` itself
        (ARCHITECTURE-BOUNDARIES.md rule 2). The lookup is scoped to the
        caller's organization on the Platform side, so an id that somehow
        named an outsider resolves to :data:`UNASSIGNED` rather than to a
        stranger's address.
        """
        keys = person_columns(definition)
        if not keys:
            return

        ids: set[uuid.UUID] = {
            value
            for key in keys
            for row in rows
            if isinstance(value := row.get(key), uuid.UUID)
        }
        directory = (
            await self._organizations.member_directory(principal.organization_id, ids)
            if ids
            else {}
        )

        for row in rows:
            for key in keys:
                raw = row.get(key)
                identity = directory.get(raw) if isinstance(raw, uuid.UUID) else None
                row[key] = identity.display_name if identity else UNASSIGNED


def _chart_info(definition: ReportDefinition) -> ChartInfo | None:
    if definition.chart is None:
        return None
    return ChartInfo(
        kind=definition.chart.kind.value,
        category_key=definition.chart.category_key,
        value_key=definition.chart.value_key,
    )


def _totals(definition: ReportDefinition, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the columns the definition marks summable.

    Only over the rows actually returned. When a report is truncated its
    totals describe the visible rows and the response says so through
    ``row_limit_reached`` — a total computed over rows the table does not show
    would be a number nobody could reconcile.
    """
    totals: dict[str, Any] = {}
    for key in definition.totals:
        values = [row.get(key) for row in rows if isinstance(row.get(key), (int, float, Decimal))]
        if not values:
            totals[key] = 0
            continue
        if any(isinstance(value, Decimal) for value in values):
            totals[key] = sum((Decimal(str(value)) for value in values), Decimal(0))
        else:
            totals[key] = sum(values)
    return totals


__all__ = ["UNASSIGNED", "ReportService"]
