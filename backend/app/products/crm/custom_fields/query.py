"""Turning a list screen's query string into custom-field SQL.

A list endpoint cannot declare its custom filters as typed parameters: which
ones exist is tenant data, decided after the code was written. So they arrive
under a reserved prefix — ``?cf_region=EMEA``, ``?cf_deal_size__gte=500`` — and
this module is what resolves them.

Resolution is the security-relevant part and happens in one order, always:

1. Split the parameter name into a field's ``api_name`` and an operator.
2. Look the ``api_name`` up in **this organization's** definitions. Anything
   that does not resolve is a 422, so an unrecognised name never reaches SQL.
3. Hand the definition and the value to
   :func:`~app.products.crm.custom_fields.filters.custom_field_filter`, which
   chooses the cast from the definition's declared type and binds both the key
   and the value as parameters.

Nothing from the request selects a column, a cast or an operator directly; the
request only *names* things that are then looked up. That is what makes an
open-ended filter surface safe to expose.

One query loads the definitions and one loads the options, whatever the number
of filters — the same two the write path makes — so filtering by six custom
fields costs no more round trips than filtering by one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import ColumnElement

from app.core.database import DbSession
from app.core.exceptions import ValidationFailedError
from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.filters import (
    FILTER_PREFIX,
    FilterOperator,
    custom_field_filter,
    sort_column,
)
from app.products.crm.custom_fields.repository import CustomFieldDefinitionRepository

#: Separates a field name from its operator: ``cf_deal_size__gte``.
#:
#: A double underscore rather than a dot or a colon, because a single one is
#: legal *inside* an api_name and the two must not be ambiguous — ``cf_deal_size``
#: is a field, ``cf_deal__size`` would be a field ``deal`` with an unknown
#: operator ``size``, and a 422 saying so is far better than quietly filtering
#: on the wrong thing.
OPERATOR_SEPARATOR = "__"

#: Ceiling on custom filters in one request.
#:
#: Each one adds a JSONB extraction and a cast to the WHERE clause. A request
#: carrying fifty of them is not a list screen; it is someone finding out how
#: expensive they can make a query.
MAX_FILTERS = 12


@dataclass(frozen=True, slots=True)
class CustomFieldQuery:
    """The custom-field half of one list request, already parsed.

    Constructed by :func:`custom_field_query`, which is the FastAPI dependency
    a list endpoint declares. Parsing happens there so a malformed parameter
    is a 422 before the handler runs; resolution happens in
    :meth:`resolve`, which needs the entity type the endpoint knows and the
    database the dependency has.
    """

    #: ``(api_name, operator, raw_value)``, in the order they were given.
    requested: tuple[tuple[str, FilterOperator, Any], ...]
    #: The ``api_name`` to sort by, when ``sort_by`` named a custom field.
    sort_field: str | None
    session: Any

    async def resolve(
        self,
        model: type[Any],
        *,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
    ) -> tuple[list[ColumnElement[bool]], ColumnElement[Any] | None]:
        """Return this request's predicates and its sort expression.

        Returns ``([], None)`` without touching the database when the request
        named no custom field at all, which is the overwhelmingly common case:
        an endpoint pays nothing for supporting this until somebody uses it.

        Raises:
            ValidationFailedError: a named field does not exist on this record
                type, or an operator or value does not apply to it.
        """
        if not self.requested and self.sort_field is None:
            return [], None

        definitions = await CustomFieldDefinitionRepository(self.session).for_entity(
            organization_id, entity_type, include_inactive=True
        )
        by_name = {definition.api_name: definition for definition in definitions}

        predicates: list[ColumnElement[bool]] = []
        for api_name, operator, raw in self.requested:
            definition = by_name.get(api_name)
            if definition is None:
                raise ValidationFailedError(
                    f"'{api_name}' is not a custom field on this record type.",
                    details={"parameter": f"{FILTER_PREFIX}{api_name}"},
                )
            # A *retired* field stays filterable on purpose: the records that
            # hold its values still exist, and a list screen is exactly where
            # somebody goes to find them before deciding what to do with them.
            predicates.append(custom_field_filter(model, definition, operator, raw))

        ordering: ColumnElement[Any] | None = None
        if self.sort_field is not None:
            definition = by_name.get(self.sort_field)
            if definition is None:
                raise ValidationFailedError(
                    f"'{self.sort_field}' is not a custom field on this record type.",
                    details={"parameter": "sort_by"},
                )
            ordering = sort_column(model, definition)

        return predicates, ordering


def custom_field_query(request: Request, session: DbSession) -> CustomFieldQuery:
    """FastAPI dependency parsing ``?cf_*`` parameters and a ``cf_`` sort key.

    Only the shape is checked here — a known operator, a bounded number of
    filters. What the names *mean* needs the tenant's definitions, so it
    happens in :meth:`CustomFieldQuery.resolve` once the endpoint has supplied
    its entity type.
    """
    requested: list[tuple[str, FilterOperator, Any]] = []

    for key in request.query_params:
        if not key.startswith(FILTER_PREFIX):
            continue
        name = key[len(FILTER_PREFIX) :]
        operator = FilterOperator.EQ
        if OPERATOR_SEPARATOR in name:
            name, _, suffix = name.rpartition(OPERATOR_SEPARATOR)
            try:
                operator = FilterOperator(suffix)
            except ValueError as exc:
                raise ValidationFailedError(
                    f"'{suffix}' is not a filter operator. Available: "
                    + ", ".join(member.value for member in FilterOperator)
                    + ".",
                    details={"parameter": key},
                ) from exc
        if not name:
            raise ValidationFailedError(
                f"'{key}' names no custom field.", details={"parameter": key}
            )

        # `getlist`, so `?cf_region=EMEA&cf_region=APAC` reaches the `in`
        # builder as two values rather than silently losing one of them.
        values: Sequence[str] = request.query_params.getlist(key)
        requested.append((name, operator, values[0] if len(values) == 1 else list(values)))

    if len(requested) > MAX_FILTERS:
        raise ValidationFailedError(
            f"At most {MAX_FILTERS} custom-field filters may be applied at once."
        )

    sort_by = request.query_params.get("sort_by")
    sort_field = (
        sort_by[len(FILTER_PREFIX) :] if sort_by and sort_by.startswith(FILTER_PREFIX) else None
    )

    return CustomFieldQuery(requested=tuple(requested), sort_field=sort_field, session=session)


#: What a list endpoint declares.
CustomFieldQueryDep = Annotated[CustomFieldQuery, Depends(custom_field_query)]

__all__ = [
    "MAX_FILTERS",
    "OPERATOR_SEPARATOR",
    "CustomFieldQuery",
    "CustomFieldQueryDep",
    "custom_field_query",
]
