"""The job queue: one table, claimed with ``FOR UPDATE SKIP LOCKED``.

PostgreSQL rather than Redis, deliberately. The requirements are tenant
context, RLS, retries, idempotency, duplicate-execution protection and job
history — and every one of those is something the database already does well:

* **History** needs a table regardless. A queue that forgets what it ran cannot
  answer "did the nightly scoring run last night", which is the first question
  anybody asks.
* **Idempotency** is a unique index.
* **Duplicate-execution protection** is ``FOR UPDATE SKIP LOCKED``: two workers
  claiming concurrently cannot take the same row, and a worker that dies holds
  no lock once its transaction ends.
* **Tenant context** is per-transaction anyway (``SET LOCAL``), and the job
  runs in a transaction.

Redis is in the stack for caching and would need a second store for the history
this table has to keep either way. One store, one transaction, no dual-write.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"

#: Attempts before a job is left FAILED for a human. Three is the usual
#: compromise: it survives a transient database blip or a restart, and it does
#: not hammer a genuinely broken handler two hundred times overnight.
DEFAULT_MAX_ATTEMPTS = 3

#: Backoff between attempts, in seconds. Explicit rather than computed so the
#: schedule is legible: a minute, five minutes, half an hour.
RETRY_BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 1800)

#: How long a claim is honoured before another worker may take the job.
#: A worker that is killed mid-job leaves ``RUNNING`` behind; without this the
#: job would be stuck forever. Long enough that a slow job is not stolen from a
#: live worker.
CLAIM_TIMEOUT_SECONDS = 900


class JobStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    #: Retries exhausted. Kept rather than deleted: a failed job is the record
    #: of something that did not happen, which is exactly what an operator
    #: needs to see.
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One unit of background work, scoped to one organization.

    Tenant-scoped like every other table holding customer data — a payload can
    name records, and an error message can quote them.

    Deliberately **not** soft-deleted: a job is a fact about what the system
    did, and the retention job removes old rows outright rather than marking
    them and keeping them forever.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        # The claim query: due, queued, oldest first.
        Index(
            "ix_jobs_status_run_at",
            "status",
            "run_at",
            postgresql_where=text("status = 'QUEUED'"),
        ),
        Index("ix_jobs_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_jobs_organization_id_job_type", "organization_id", "job_type"),
        # **The duplicate-execution guarantee.** Two enqueues carrying the same
        # key for the same organization collapse into one row, so a scheduler
        # that ticks twice — or two schedulers racing — cannot double-run a
        # nightly job. Partial, so a completed job's key is released and the
        # same recurring job can be enqueued again next period.
        Index(
            "uq_jobs_organization_id_idempotency_key_live",
            "organization_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text(
                "idempotency_key IS NOT NULL AND status IN ('QUEUED', 'RUNNING')"
            ),
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        {"schema": PLATFORM_SCHEMA},
    )

    #: Registry key naming the handler, e.g. ``crm.recompute_campaign_metrics``.
    #: Text rather than an enum so registering a handler is code, not a
    #: migration — and so a job row survives its handler being renamed, which
    #: is a state an operator needs to be able to see rather than one that
    #: breaks the enum.
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", schema=PLATFORM_SCHEMA, native_enum=True),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default=JobStatus.QUEUED.value,
    )
    #: Handler arguments. JSONB rather than columns because each handler wants
    #: something different, and a job's payload is opaque to the queue.
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    #: Earliest instant this job may run. A queue and a scheduler are the same
    #: thing once jobs carry a due time — "run now" is simply ``run_at = now``.
    run_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_ATTEMPTS, server_default="3"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Set when a worker claims the job, cleared when it finishes. Together
    #: with ``CLAIM_TIMEOUT_SECONDS`` this is what lets a job orphaned by a
    #: killed worker be retried rather than stranded in RUNNING.
    locked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Free-form summary the handler returns, e.g. how many records it touched.
    #: Read by operators and by the tests; nothing branches on it.
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)

    def next_backoff(self) -> int:
        """Seconds to wait before the attempt after this one."""
        index = min(self.attempts, len(RETRY_BACKOFF_SECONDS)) - 1
        return RETRY_BACKOFF_SECONDS[max(index, 0)]


__all__ = [
    "CLAIM_TIMEOUT_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "RETRY_BACKOFF_SECONDS",
    "Job",
    "JobStatus",
]
