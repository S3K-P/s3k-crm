"""CRM reporting: source attribution, win/loss, and pipeline ageing.

S3K can answer these because ``lead_sources`` is an **entity**, not a picklist
(analysis §4.6). Zoho's Lead Source is a picklist value, which is exactly why
Zoho cannot report cost-per-lead or source ROI without a spreadsheet — there is
no row to attach a cost to. Leaning on that difference is the point.

Everything here is a scoped aggregate. Nothing loads rows to count them in
Python, and every query filters on ``organization_id`` and applies the caller's
record-level visibility, so a report can never total figures its reader is not
allowed to open.

Deliberately **not** a BI system (analysis §6.6): a fixed set of questions a
sales manager actually asks, answered in SQL, rather than a query builder.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.leads.models import Lead, LeadSource, LeadStatus
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.shared.visibility import RecordVisibility

#: Ageing buckets, in days. Chosen to match how people talk about a pipeline:
#: this month, last month, the quarter, and "why is this still open".
AGEING_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("0-30 days", 0, 30),
    ("31-60 days", 31, 60),
    ("61-90 days", 61, 90),
    ("over 90 days", 91, None),
)


@dataclass(frozen=True, slots=True)
class SourcePerformance:
    """One lead source, and what it produced."""

    lead_source_id: uuid.UUID | None
    name: str
    leads: int
    qualified: int
    converted: int
    opportunities: int
    won: int
    won_value: Decimal
    open_value: Decimal

    @property
    def qualification_rate(self) -> float:
        return round(self.qualified / self.leads * 100, 1) if self.leads else 0.0

    @property
    def conversion_rate(self) -> float:
        """Leads that became a customer relationship, as a percentage."""
        return round(self.converted / self.leads * 100, 1) if self.leads else 0.0

    @property
    def win_rate(self) -> float:
        return round(self.won / self.opportunities * 100, 1) if self.opportunities else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "lead_source_id": str(self.lead_source_id) if self.lead_source_id else None,
            "name": self.name,
            "leads": self.leads,
            "qualified": self.qualified,
            "converted": self.converted,
            "opportunities": self.opportunities,
            "won": self.won,
            "won_value": str(self.won_value),
            "open_value": str(self.open_value),
            "qualification_rate": self.qualification_rate,
            "conversion_rate": self.conversion_rate,
            "win_rate": self.win_rate,
        }


class ReportingRepository:
    """Scoped aggregates for the reporting screens."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _scoped(
        statement: Select[Any], visibility: RecordVisibility | None, model: type[Any]
    ) -> Select[Any]:
        if visibility is None:
            return statement
        predicate = visibility.filter_for(model)
        return statement if predicate is None else statement.where(predicate)

    async def source_performance(
        self,
        organization_id: uuid.UUID,
        *,
        lead_visibility: RecordVisibility | None = None,
        opportunity_visibility: RecordVisibility | None = None,
    ) -> list[SourcePerformance]:
        """Per-source funnel: leads → qualified → converted → won.

        Two grouped queries rather than one join. Joining leads to
        opportunities through the source would multiply rows — a source with
        ten leads and three deals would count each lead three times — and
        producing a wrong number quietly is worse than issuing a second query.
        """
        lead_rows = await self._session.execute(
            self._scoped(
                select(
                    Lead.lead_source_id,
                    func.count(),
                    func.count().filter(Lead.status == LeadStatus.QUALIFIED),
                    func.count().filter(Lead.converted_at.is_not(None)),
                )
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                )
                .group_by(Lead.lead_source_id),
                lead_visibility,
                Lead,
            )
        )
        leads_by_source = {
            row[0]: (int(row[1]), int(row[2]), int(row[3])) for row in lead_rows.all()
        }

        opportunity_rows = await self._session.execute(
            self._scoped(
                select(
                    Opportunity.lead_source_id,
                    func.count(),
                    func.count().filter(Opportunity.won_at.is_not(None)),
                    func.coalesce(
                        func.sum(
                            case(
                                (Opportunity.won_at.is_not(None), Opportunity.deal_value),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    and_(
                                        Opportunity.won_at.is_(None),
                                        Opportunity.lost_at.is_(None),
                                    ),
                                    Opportunity.deal_value,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                )
                .where(
                    Opportunity.organization_id == organization_id,
                    Opportunity.deleted_at.is_(None),
                )
                .group_by(Opportunity.lead_source_id),
                opportunity_visibility,
                Opportunity,
            )
        )
        deals_by_source = {
            row[0]: (int(row[1]), int(row[2]), Decimal(str(row[3])), Decimal(str(row[4])))
            for row in opportunity_rows.all()
        }

        names = await self._source_names(organization_id)

        performance: list[SourcePerformance] = []
        for source_id in set(leads_by_source) | set(deals_by_source):
            leads, qualified, converted = leads_by_source.get(source_id, (0, 0, 0))
            deals, won, won_value, open_value = deals_by_source.get(
                source_id, (0, 0, Decimal(0), Decimal(0))
            )
            performance.append(
                SourcePerformance(
                    lead_source_id=source_id,
                    # A NULL source is real and worth naming rather than
                    # hiding: "how much of our pipeline has no attribution at
                    # all" is one of the more useful things this report says.
                    name=names.get(source_id, "Unattributed") if source_id else "Unattributed",
                    leads=leads,
                    qualified=qualified,
                    converted=converted,
                    opportunities=deals,
                    won=won,
                    won_value=won_value,
                    open_value=open_value,
                )
            )
        performance.sort(key=lambda row: (-row.won_value, -row.leads, row.name))
        return performance

    async def _source_names(self, organization_id: uuid.UUID) -> dict[uuid.UUID, str]:
        result = await self._session.execute(
            select(LeadSource.id, LeadSource.name).where(
                LeadSource.organization_id == organization_id,
                LeadSource.deleted_at.is_(None),
            )
        )
        return {row[0]: str(row[1]) for row in result.all()}

    async def win_loss(
        self,
        organization_id: uuid.UUID,
        *,
        since: dt.datetime | None = None,
        visibility: RecordVisibility | None = None,
    ) -> dict[str, Any]:
        """Won and lost counts and values, with the top loss reasons."""
        statement = select(
            func.count().filter(Opportunity.won_at.is_not(None)),
            func.count().filter(Opportunity.lost_at.is_not(None)),
            func.coalesce(
                func.sum(
                    case((Opportunity.won_at.is_not(None), Opportunity.deal_value), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((Opportunity.lost_at.is_not(None), Opportunity.deal_value), else_=0)
                ),
                0,
            ),
        ).where(
            Opportunity.organization_id == organization_id,
            Opportunity.deleted_at.is_(None),
        )
        if since is not None:
            statement = statement.where(
                func.coalesce(Opportunity.won_at, Opportunity.lost_at) >= since
            )
        row = (await self._session.execute(
            self._scoped(statement, visibility, Opportunity)
        )).one()

        won, lost, won_value, lost_value = int(row[0]), int(row[1]), row[2], row[3]
        closed = won + lost

        reasons = await self._session.execute(
            self._scoped(
                select(Opportunity.loss_reason, func.count())
                .where(
                    Opportunity.organization_id == organization_id,
                    Opportunity.deleted_at.is_(None),
                    Opportunity.lost_at.is_not(None),
                    Opportunity.loss_reason.is_not(None),
                )
                .group_by(Opportunity.loss_reason)
                .order_by(func.count().desc())
                .limit(10),
                visibility,
                Opportunity,
            )
        )

        return {
            "won": won,
            "lost": lost,
            "won_value": str(Decimal(str(won_value))),
            "lost_value": str(Decimal(str(lost_value))),
            "win_rate": round(won / closed * 100, 1) if closed else 0.0,
            "loss_reasons": [
                {"reason": str(reason), "count": int(count)}
                for reason, count in reasons.all()
            ],
        }

    async def pipeline_ageing(
        self,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility | None = None,
    ) -> list[dict[str, Any]]:
        """How long open deals have been sitting, bucketed.

        Age is measured from creation rather than from the last stage change:
        "this deal has been open four months" is the question, and a deal
        nudged between stages without progressing is exactly the one the report
        should surface rather than reset.
        """
        age_days = func.extract("day", func.now() - Opportunity.created_at)
        buckets = case(
            *[
                (
                    age_days.between(low, high) if high is not None else age_days >= low,
                    label,
                )
                for label, low, high in AGEING_BUCKETS
            ],
            else_="unknown",
        ).label("bucket")

        result = await self._session.execute(
            self._scoped(
                select(
                    buckets,
                    func.count(),
                    func.coalesce(func.sum(Opportunity.deal_value), 0),
                )
                .where(
                    Opportunity.organization_id == organization_id,
                    Opportunity.deleted_at.is_(None),
                    Opportunity.won_at.is_(None),
                    Opportunity.lost_at.is_(None),
                )
                .group_by(buckets),
                visibility,
                Opportunity,
            )
        )
        counts = {str(row[0]): (int(row[1]), Decimal(str(row[2]))) for row in result.all()}

        # Every bucket is returned, including the empty ones: a gap in the
        # middle of an ageing chart reads as missing data rather than as zero.
        return [
            {
                "bucket": label,
                "count": counts.get(label, (0, Decimal(0)))[0],
                "value": str(counts.get(label, (0, Decimal(0)))[1]),
            }
            for label, _, _ in AGEING_BUCKETS
        ]

    async def stage_conversion(
        self,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility | None = None,
    ) -> list[dict[str, Any]]:
        """How many deals currently sit in each stage, open and closed.

        The shape of the funnel. Reads the live stage rather than the history
        table, which answers "where is the pipeline now" — history answers
        "how fast does it move", which is a different report.
        """
        result = await self._session.execute(
            self._scoped(
                select(
                    PipelineStage.name,
                    PipelineStage.sort_order,
                    func.count(Opportunity.id),
                    func.coalesce(func.sum(Opportunity.deal_value), 0),
                )
                .select_from(PipelineStage)
                .outerjoin(
                    Opportunity,
                    (Opportunity.stage_id == PipelineStage.id)
                    & (Opportunity.deleted_at.is_(None)),
                )
                .where(
                    PipelineStage.organization_id == organization_id,
                    PipelineStage.deleted_at.is_(None),
                )
                .group_by(PipelineStage.name, PipelineStage.sort_order)
                .order_by(PipelineStage.sort_order),
                visibility,
                Opportunity,
            )
        )
        return [
            {
                "stage": str(row[0]),
                "sort_order": int(row[1]),
                "count": int(row[2]),
                "value": str(Decimal(str(row[3]))),
            }
            for row in result.all()
        ]


__all__ = ["AGEING_BUCKETS", "ReportingRepository", "SourcePerformance"]
