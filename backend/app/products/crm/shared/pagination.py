"""Pagination, sorting and the standard list envelope.

Offset pagination is used rather than the cursor scheme sketched in doc 11:
the CRM list screens are page-numbered with a total count, which a cursor
cannot provide. Cursor pagination is the right answer for large exports and can
be added alongside this without changing existing responses.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 25

SortDirection = Literal["asc", "desc"]


class PageParams(BaseModel):
    """Query parameters shared by every list endpoint."""

    page: int = Field(default=1, ge=1, description="1-based page number.")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Items per page (max {MAX_PAGE_SIZE}).",
    )
    sort_by: str | None = Field(default=None, description="Column to sort on.")
    sort_dir: SortDirection = Field(default="desc", description="Sort direction.")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    sort_by: Annotated[str | None, Query()] = None,
    sort_dir: Annotated[SortDirection, Query()] = "desc",
) -> PageParams:
    """FastAPI dependency producing :class:`PageParams` from the query string."""
    return PageParams(page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir)


class PageMeta(BaseModel):
    """Pagination metadata returned alongside every list payload."""

    page: int
    page_size: int
    total: int
    total_pages: int
    has_more: bool


class Page[T](BaseModel):
    """The standard list envelope: ``{"data": [...], "pagination": {...}}``."""

    data: list[T]
    pagination: PageMeta

    @classmethod
    def build(cls, items: list[T], *, total: int, params: PageParams) -> Page[T]:
        total_pages = (total + params.page_size - 1) // params.page_size if total else 0
        return cls(
            data=items,
            pagination=PageMeta(
                page=params.page,
                page_size=params.page_size,
                total=total,
                total_pages=total_pages,
                has_more=params.page * params.page_size < total,
            ),
        )


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "Page",
    "PageMeta",
    "PageParams",
    "SortDirection",
    "page_params",
]
