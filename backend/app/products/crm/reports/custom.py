"""The custom-report engine — running a user-authored report definition.

Four steps, and they are the same four steps :mod:`.service` documents for
the built-in catalogue, because this module deliberately does not invent a
second security model:

1. **The definition names one entity.** Fields, the filter group, the group
   key and every aggregation are resolved against :mod:`.fields`' registry
   for that entity — the request never supplies a column, only a key looked
   up in an allow-list.
2. **The caller is authorized against that entity's own module** —
   ``leads.VIEW``, ``opportunities.VIEW`` and so on — not against a
   ``reports`` permission. Same reasoning as :mod:`.catalog`'s own module
   docstring.
3. **Record-level visibility is resolved for that module** and applied
   inside the query — the WHERE clause, never a filter on the result.
4. **Owner ids are resolved to names** before anything leaves this layer,
   through the Platform directory, exactly as :meth:`.service.ReportService._resolve_people`
   does.

Aggregation happens in PostgreSQL: ``GROUP BY`` plus ``count``/``sum``/
``avg``/``min``/``max``, never a Python loop over fetched rows. A row-listing
report (no ``group_by``) is capped at :data:`~.repository.MAX_REPORT_ROWS`
the same way the catalogue's own row-per-record reports are.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import PermissionDeniedError
from app.platform.organizations.service import organizations_for_session
from app.products.crm.custom_fields.models import CustomFieldDefinition
from app.products.crm.custom_fields.repository import CustomFieldDefinitionRepository
from app.products.crm.layouts.catalog import custom_field_api_name, is_custom_field_key
from app.products.crm.reports.catalog import ColumnType
from app.products.crm.reports.conditions import (
    ReportCondition,
    ReportFilterGroup,
    build_condition,
    combine,
)
from app.products.crm.reports.fields import (
    CRM_ENTITY_TYPE_FOR_ENTITY,
    DEFAULT_DATE_FIELD,
    MODEL_FOR_ENTITY,
    MODULE_FOR_ENTITY,
    AggOp,
    ReportEntity,
    ReportField,
    field_for,
)
from app.products.crm.reports.policies import VIEW
from app.products.crm.reports.repository import MAX_REPORT_ROWS
from app.products.crm.reports.schemas import (
    AvailableFieldInfo,
    ChartInfo,
    CustomReportDefinition,
    ReportAggregation,
    ReportColumnInfo,
    ReportResult,
)
from app.products.crm.shared.visibility import RecordVisibility

_AGG_SQL: dict[AggOp, Any] = {
    AggOp.SUM: func.sum,
    AggOp.AVG: func.avg,
    AggOp.MIN: func.min,
    AggOp.MAX: func.max,
}

_UNASSIGNED = "Unassigned"


def _resolve_field(entity: ReportEntity, key: str) -> ReportField:
    """A built-in field only — custom fields are handled separately.

    Raises:
        ValidationFailedError: ``key`` is not offered for ``entity``, or is a
            ``custom:`` key (not valid where only a built-in field applies —
            a group key or an aggregation target, in this first version; see
            ``.fields``'s module docstring).
    """
    if is_custom_field_key(key):
        msg = f"'{key}' is a custom field and cannot be used here."
        raise ValidationFailedError(msg)
    try:
        return field_for(entity, key)
    except KeyError as exc:
        msg = f"'{key}' is not a field on {entity.value.title()}."
        raise ValidationFailedError(msg) from exc


def validate_definition(definition: CustomReportDefinition) -> None:
    """Check every field/operator/aggregation the definition names actually
    exists and applies, without running any SQL.

    Called both when a report is saved (so a broken definition is a 422 at
    save time, not a 500 the next time somebody opens a dashboard) and before
    :meth:`CustomReportEngine.run` builds a statement from it.
    """
    entity = definition.entity

    for key in definition.fields:
        if not is_custom_field_key(key):
            _resolve_field(entity, key)

    if definition.filters is not None:
        # Only the built-in half — a `custom:` condition is checked when the
        # report actually runs, once an organization_id is available to
        # resolve it against (see `_custom_field_definitions`).
        validate_builtin_filter_group(entity, definition.filters)

    if definition.group_by is not None:
        group_field = _resolve_field(entity, definition.group_by)
        if not group_field.groupable:
            msg = f"'{group_field.label}' cannot be grouped by."
            raise ValidationFailedError(msg)
        if definition.group_by_interval is not None and group_field.type is not ColumnType.DATE:
            msg = "group_by_interval only applies to a date field."
            raise ValidationFailedError(msg)

    for aggregation in definition.aggregations:
        if aggregation.field is None:
            continue
        field = _resolve_field(entity, aggregation.field)
        if aggregation.op not in field.aggregations:
            msg = f"'{aggregation.op.value}' does not apply to '{field.label}'."
            raise ValidationFailedError(msg)

    if definition.sort_by is not None and not is_custom_field_key(definition.sort_by):
        # A sort key must be one of the report's own output columns — the
        # group key, an aggregation's own key, or (row-listing) a selected
        # field — not an arbitrary field on the entity. Checked precisely in
        # `_build_statement`, where the output key set is actually known;
        # here only its existence as *a* field is confirmed so a client typo
        # is a 422 rather than a query built against nothing.
        pass

    date_field_key = definition.date_field or DEFAULT_DATE_FIELD
    date_field = _resolve_field(entity, date_field_key)
    if date_field.type is not ColumnType.DATE:
        msg = f"'{date_field.label}' is not a date field."
        raise ValidationFailedError(msg)


def validate_builtin_filter_group(entity: ReportEntity, group: ReportFilterGroup) -> None:
    """Check every *built-in* field/operator a filter group names.

    Used both by the custom-report definition (via :func:`validate_definition`)
    and, directly, by ``views.schemas`` when a saved view carries an advanced
    filter — see that module for why a ``custom:`` condition is skipped here
    rather than resolved: it needs the organization's own field definitions,
    which a synchronous Pydantic validator has no session to fetch.
    """
    for condition in group.conditions:
        if is_custom_field_key(condition.field):
            continue
        field = _resolve_field(entity, condition.field)
        if not field.filterable:
            msg = f"'{field.label}' cannot be filtered on."
            raise ValidationFailedError(msg)
        # `build_condition` itself checks operator legality against the
        # field's type; running it here (with today's date; the actual value
        # is never bound to SQL from this call) catches a bad operator/value
        # combination at save time rather than the first time the view runs.
        build_condition(field, condition, today=dt.date.today())


def _output_key(aggregation: ReportAggregation) -> str:
    return f"{aggregation.field or 'all'}__{aggregation.op.value.lower()}"


def _agg_output_type(op: AggOp, field_type: ColumnType | None) -> ColumnType:
    if op is AggOp.COUNT:
        return ColumnType.NUMBER
    assert field_type is not None  # noqa: S101 - validated by ReportAggregation itself
    return field_type


async def build_advanced_filter_predicate(
    session: AsyncSession,
    organization_id: uuid.UUID,
    entity: ReportEntity,
    group: ReportFilterGroup,
) -> ColumnElement[bool] | None:
    """The one predicate a saved view's (or a list endpoint's own) advanced
    filter contributes to a query — the same condition/group machinery the
    custom-report engine runs on, reused rather than re-implemented so a
    field, an operator or a custom-field lookup behaves identically whether
    it is filtering a report or a list screen.

    Returns ``None`` for an empty group, so a caller can add it to a filter
    list unconditionally (``if predicate is not None: filters.append(...)``)
    without a branch of its own.
    """
    if not group.conditions:
        return None
    model = MODEL_FOR_ENTITY[entity]
    custom_keys = {c.field for c in group.conditions if is_custom_field_key(c.field)}
    custom_definitions: dict[str, CustomFieldDefinition] = {}
    if custom_keys:
        crm_entity_type = CRM_ENTITY_TYPE_FOR_ENTITY[entity]
        if crm_entity_type is None:
            msg = f"{entity.value.title()} has no custom fields to filter by."
            raise ValidationFailedError(msg)
        api_names = {custom_field_api_name(key) for key in custom_keys}
        available = await CustomFieldDefinitionRepository(session).for_entity(
            organization_id, crm_entity_type, include_inactive=False
        )
        by_name = {d.api_name: d for d in available if d.api_name in api_names}
        missing = api_names - set(by_name)
        if missing:
            msg = f"Unknown custom field(s): {', '.join(sorted(missing))}."
            raise ValidationFailedError(msg)
        custom_definitions = by_name

    today = dt.datetime.now(dt.UTC).date()
    predicates: list[ColumnElement[bool]] = []
    for condition in group.conditions:
        if is_custom_field_key(condition.field):
            found = custom_definitions[custom_field_api_name(condition.field)]
            predicates.append(
                build_condition(
                    None, condition, today=today, custom_definition=found, custom_model=model
                )
            )
        else:
            field = _resolve_field(entity, condition.field)
            if not field.filterable:
                msg = f"'{field.label}' cannot be filtered on."
                raise ValidationFailedError(msg)
            predicates.append(build_condition(field, condition, today=today))
    return combine(predicates, logic=group.logic)


class CustomReportEngine:
    """Validates and runs one :class:`CustomReportDefinition`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._organizations = organizations_for_session(session)
        self._definitions = CustomFieldDefinitionRepository(session)

    # --- Field discovery, for the builder ----------------------------------

    async def available_fields(
        self, organization_id: uuid.UUID, entity: ReportEntity
    ) -> list[AvailableFieldInfo]:
        result = [
            AvailableFieldInfo(
                key=field.key,
                label=field.label,
                type=field.type.value,
                is_custom=False,
                filterable=field.filterable,
                groupable=field.groupable,
                sortable=field.sortable,
                aggregations=[op.value for op in sorted(field.aggregations, key=str)],
            )
            for field in _fields_in_order(entity)
        ]
        crm_entity_type = CRM_ENTITY_TYPE_FOR_ENTITY[entity]
        if crm_entity_type is not None:
            definitions = await self._definitions.for_entity(
                organization_id, crm_entity_type, include_inactive=False
            )
            result.extend(
                AvailableFieldInfo(
                    key=f"custom:{definition.api_name}",
                    label=definition.label,
                    type="TEXT",
                    is_custom=True,
                    filterable=True,
                    groupable=False,
                    sortable=False,
                    aggregations=[],
                )
                for definition in definitions
            )
        return result

    # --- Running -------------------------------------------------------

    async def run(
        self,
        definition: CustomReportDefinition,
        principal: Principal,
        *,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        today: dt.date | None = None,
    ) -> ReportResult:
        validate_definition(definition)

        module = MODULE_FOR_ENTITY[definition.entity]
        if not principal.has_permission(module, VIEW):
            raise PermissionDeniedError

        visibility = RecordVisibility.for_module(principal, module)
        today = today or dt.datetime.now(dt.UTC).date()

        custom_definitions = await self._custom_field_definitions(
            principal.organization_id, definition
        )

        if definition.group_by is not None:
            rows, columns, chart, totals, truncated = await self._run_grouped(
                definition,
                principal.organization_id,
                visibility=visibility,
                date_from=date_from,
                date_to=date_to,
                today=today,
                custom_definitions=custom_definitions,
            )
        else:
            rows, columns, truncated = await self._run_listing(
                definition,
                principal.organization_id,
                visibility=visibility,
                date_from=date_from,
                date_to=date_to,
                today=today,
                custom_definitions=custom_definitions,
            )
            chart = None
            totals = {}

        await self._resolve_people(principal.organization_id, columns, rows)

        name = "Custom report"
        return ReportResult(
            key="custom",
            name=name,
            description="",
            category="Custom",
            generated_at=dt.datetime.now(dt.UTC),
            columns=columns,
            rows=rows,
            totals=totals,
            chart=chart,
            date_from=date_from,
            date_to=date_to,
            row_limit_reached=truncated,
        )

    # --- Statement building --------------------------------------------

    async def _custom_field_definitions(
        self, organization_id: uuid.UUID, definition: CustomReportDefinition
    ) -> dict[str, CustomFieldDefinition]:
        """``api_name`` -> definition, for every ``custom:`` key the report names."""
        keys: set[str] = set()
        if definition.filters:
            keys |= {c.field for c in definition.filters.conditions if is_custom_field_key(c.field)}
        keys |= {f for f in definition.fields if is_custom_field_key(f)}
        if not keys:
            return {}
        crm_entity_type = CRM_ENTITY_TYPE_FOR_ENTITY[definition.entity]
        if crm_entity_type is None:
            msg = f"{definition.entity.value.title()} has no custom fields to filter by."
            raise ValidationFailedError(msg)
        api_names = {custom_field_api_name(key) for key in keys}
        available = await self._definitions.for_entity(
            organization_id, crm_entity_type, include_inactive=False
        )
        by_name = {d.api_name: d for d in available if d.api_name in api_names}
        missing = api_names - set(by_name)
        if missing:
            msg = f"Unknown custom field(s): {', '.join(sorted(missing))}."
            raise ValidationFailedError(msg)
        return by_name

    def _base_query(
        self,
        entity: ReportEntity,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility,
        joins: dict[type[Any], Any],
    ) -> Select[Any]:
        model = MODEL_FOR_ENTITY[entity]
        statement = select(model).where(
            model.organization_id == organization_id, model.deleted_at.is_(None)
        )
        predicate = visibility.filter_for(model)
        if predicate is not None:
            statement = statement.where(predicate)
        for join in joins.values():
            statement = statement.join(join.model, join.on, isouter=join.outer)
        return statement

    def _collect_joins(
        self, entity: ReportEntity, definition: CustomReportDefinition
    ) -> dict[type[Any], Any]:
        joins: dict[type[Any], Any] = {}

        def note(key: str) -> None:
            if is_custom_field_key(key):
                return
            field = field_for(entity, key)
            if field.join is not None:
                joins[field.join.model] = field.join

        for key in definition.fields:
            note(key)
        if definition.group_by:
            note(definition.group_by)
        for aggregation in definition.aggregations:
            if aggregation.field:
                note(aggregation.field)
        if definition.sort_by:
            note(definition.sort_by)
        if definition.filters:
            for condition in definition.filters.conditions:
                note(condition.field)
        return joins

    def _apply_filters(
        self,
        statement: Select[Any],
        entity: ReportEntity,
        definition: CustomReportDefinition,
        *,
        today: dt.date,
        custom_definitions: dict[str, CustomFieldDefinition],
    ) -> Select[Any]:
        if not definition.filters or not definition.filters.conditions:
            return statement
        model = MODEL_FOR_ENTITY[entity]
        predicates: list[ColumnElement[bool]] = []
        for condition in definition.filters.conditions:
            predicates.append(
                self._condition_predicate(
                    entity, model, condition, today=today, custom_definitions=custom_definitions
                )
            )
        combined = combine(predicates, logic=definition.filters.logic)
        return statement if combined is None else statement.where(combined)

    def _condition_predicate(
        self,
        entity: ReportEntity,
        model: type[Any],
        condition: ReportCondition,
        *,
        today: dt.date,
        custom_definitions: dict[str, CustomFieldDefinition],
    ) -> ColumnElement[bool]:
        if is_custom_field_key(condition.field):
            api_name = custom_field_api_name(condition.field)
            found = custom_definitions.get(api_name)
            if found is None:  # pragma: no cover - resolved in _custom_field_definitions
                msg = f"Unknown custom field: {api_name}."
                raise ValidationFailedError(msg)
            return build_condition(
                None, condition, today=today, custom_definition=found, custom_model=model
            )
        field = _resolve_field(entity, condition.field)
        if not field.filterable:
            msg = f"'{field.label}' cannot be filtered on."
            raise ValidationFailedError(msg)
        return build_condition(field, condition, today=today)

    def _apply_date_window(
        self,
        statement: Select[Any],
        entity: ReportEntity,
        definition: CustomReportDefinition,
        *,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> Select[Any]:
        if date_from is None and date_to is None:
            return statement
        field = _resolve_field(entity, definition.date_field or DEFAULT_DATE_FIELD)
        if date_from is not None:
            statement = statement.where(func.date(field.column) >= date_from)
        if date_to is not None:
            statement = statement.where(func.date(field.column) <= date_to)
        return statement

    async def _run_listing(
        self,
        definition: CustomReportDefinition,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility,
        date_from: dt.date | None,
        date_to: dt.date | None,
        today: dt.date,
        custom_definitions: dict[str, CustomFieldDefinition],
    ) -> tuple[list[dict[str, Any]], list[ReportColumnInfo], bool]:
        entity = definition.entity
        joins = self._collect_joins(entity, definition)
        statement = self._base_query(entity, organization_id, visibility=visibility, joins=joins)
        statement = self._apply_filters(
            statement, entity, definition, today=today, custom_definitions=custom_definitions
        )
        statement = self._apply_date_window(
            statement, entity, definition, date_from=date_from, date_to=date_to
        )

        output_fields = [_resolve_field(entity, key) for key in definition.fields]
        statement = statement.with_only_columns(
            *(field.column.label(field.key) for field in output_fields)
        )

        if definition.sort_by is not None:
            sort_field = next((f for f in output_fields if f.key == definition.sort_by), None)
            if sort_field is None or not sort_field.sortable:
                msg = f"'{definition.sort_by}' cannot be sorted on."
                raise ValidationFailedError(msg)
            column = sort_field.column
            statement = statement.order_by(
                column.desc() if definition.sort_dir == "desc" else column.asc()
            )
        else:
            date_field = _resolve_field(entity, definition.date_field or DEFAULT_DATE_FIELD)
            statement = statement.order_by(date_field.column.desc())

        result = await self._session.execute(statement.limit(MAX_REPORT_ROWS + 1))
        raw_rows = result.mappings().all()
        truncated = len(raw_rows) > MAX_REPORT_ROWS
        rows = [dict(row) for row in raw_rows[:MAX_REPORT_ROWS]]
        columns = [
            ReportColumnInfo(key=field.key, label=field.label, type=field.type.value)
            for field in output_fields
        ]
        return rows, columns, truncated

    async def _run_grouped(
        self,
        definition: CustomReportDefinition,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility,
        date_from: dt.date | None,
        date_to: dt.date | None,
        today: dt.date,
        custom_definitions: dict[str, CustomFieldDefinition],
    ) -> tuple[
        list[dict[str, Any]], list[ReportColumnInfo], ChartInfo | None, dict[str, Any], bool
    ]:
        entity = definition.entity
        assert definition.group_by is not None  # noqa: S101 - guarded by validate_definition
        joins = self._collect_joins(entity, definition)
        statement = self._base_query(entity, organization_id, visibility=visibility, joins=joins)
        statement = self._apply_filters(
            statement, entity, definition, today=today, custom_definitions=custom_definitions
        )
        statement = self._apply_date_window(
            statement, entity, definition, date_from=date_from, date_to=date_to
        )

        group_field = _resolve_field(entity, definition.group_by)
        group_expr = (
            func.date_trunc(definition.group_by_interval.value, group_field.column)
            if definition.group_by_interval
            else group_field.column
        )
        group_label = "group"

        agg_exprs: list[Any] = []
        agg_types: dict[str, ColumnType] = {}
        for aggregation in definition.aggregations:
            key = _output_key(aggregation)
            expr: Any
            if aggregation.op is AggOp.COUNT:
                field_type = None
                expr = (
                    func.count(_resolve_field(entity, aggregation.field).column)
                    if aggregation.field
                    else func.count()
                )
            else:
                assert aggregation.field is not None  # noqa: S101 - ReportAggregation validates this
                field = _resolve_field(entity, aggregation.field)
                field_type = field.type
                sql_fn = _AGG_SQL[aggregation.op]
                expr = sql_fn(field.column)
                if aggregation.op is AggOp.SUM:
                    expr = func.coalesce(expr, 0)
            agg_exprs.append(expr.label(key))
            agg_types[key] = _agg_output_type(aggregation.op, field_type)

        statement = statement.with_only_columns(group_expr.label(group_label), *agg_exprs).group_by(
            group_expr
        )

        sort_keys = {group_label, *agg_types}
        if definition.sort_by is not None:
            if definition.sort_by not in sort_keys:
                msg = f"'{definition.sort_by}' is not a column of this report."
                raise ValidationFailedError(msg)
            order_column = group_expr if definition.sort_by == group_label else next(
                e for e in agg_exprs if e.name == definition.sort_by
            )
            direction = definition.sort_dir
        else:
            order_column = agg_exprs[0] if agg_exprs else group_expr
            direction = "desc" if agg_exprs else "asc"
        statement = statement.order_by(
            order_column.desc() if direction == "desc" else order_column.asc()
        )

        result = await self._session.execute(statement.limit(MAX_REPORT_ROWS + 1))
        raw_rows = result.mappings().all()
        truncated = len(raw_rows) > MAX_REPORT_ROWS
        rows = [dict(row) for row in raw_rows[:MAX_REPORT_ROWS]]

        group_type = ColumnType.DATE if definition.group_by_interval else group_field.type
        columns = [
            ReportColumnInfo(key=group_label, label=group_field.label, type=group_type.value)
        ]
        for aggregation in definition.aggregations:
            key = _output_key(aggregation)
            if aggregation.op is AggOp.COUNT and aggregation.field is None:
                label = "Count"
            elif aggregation.field:
                agg_field_label = _resolve_field(entity, aggregation.field).label
                label = f"{aggregation.op.value.title()} of {agg_field_label}"
            else:
                label = aggregation.op.value.title()
            columns.append(ReportColumnInfo(key=key, label=label, type=agg_types[key].value))

        totals: dict[str, Any] = {}
        for aggregation in definition.aggregations:
            if aggregation.op not in (AggOp.SUM, AggOp.COUNT):
                continue
            key = _output_key(aggregation)
            values = [
                row.get(key) for row in rows if isinstance(row.get(key), (int, float, Decimal))
            ]
            if not values:
                totals[key] = 0
                continue
            totals[key] = (
                sum((Decimal(str(v)) for v in values), Decimal(0))
                if any(isinstance(v, Decimal) for v in values)
                else sum(values)
            )

        chart: ChartInfo | None = None
        if definition.chart_kind and agg_exprs:
            first_key = _output_key(definition.aggregations[0])
            chart = ChartInfo(
                kind=definition.chart_kind, category_key=group_label, value_key=first_key
            )

        return rows, columns, chart, totals, truncated

    # --- Person resolution -----------------------------------------------

    async def _resolve_people(
        self,
        organization_id: uuid.UUID,
        columns: list[ReportColumnInfo],
        rows: list[dict[str, Any]],
    ) -> None:
        person_keys = [
            column.key for column in columns if column.type == ColumnType.PERSON.value
        ]
        if not person_keys:
            return
        ids: set[uuid.UUID] = {
            value
            for key in person_keys
            for row in rows
            if isinstance(value := row.get(key), uuid.UUID)
        }
        if not ids:
            return
        directory = await self._organizations.member_directory(organization_id, ids)
        for row in rows:
            for key in person_keys:
                raw = row.get(key)
                identity = directory.get(raw) if isinstance(raw, uuid.UUID) else None
                row[key] = identity.display_name if identity else _UNASSIGNED


def _fields_in_order(entity: ReportEntity) -> list[ReportField]:
    from app.products.crm.reports.fields import FIELDS

    return list(FIELDS[entity].values())


__all__ = [
    "CustomReportEngine",
    "build_advanced_filter_predicate",
    "validate_builtin_filter_group",
    "validate_definition",
]
