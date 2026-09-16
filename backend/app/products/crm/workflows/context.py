"""Loop / re-entrancy protection for chained workflow writes (Step 13).

A workflow action can itself write a record — ``UPDATE_FIELD``, ``ASSIGN_OWNER``,
``CHANGE_STAGE`` and ``CHANGE_STATUS`` all go through the entity's own service,
the same one a human request uses, and that service enqueues the same
``crm.record.event_occurred`` a human's write would. Without something to stop
it, workflow A ("status changes -> set priority") and workflow B ("priority
changes -> set status") would retrigger each other forever.

**The mechanism is a depth counter threaded through a context variable, not a
lock or a "rule already ran" flag.** A lock would serialize unrelated
workflows; a per-rule flag would not stop *different* rules from chaining
into each other (A -> B -> C -> A). Depth stops any chain, of any shape, after
a fixed number of hops — and does it without a table to clean up, since a
``ContextVar`` is naturally scoped to one async task and needs no teardown
beyond ``reset``.

**How the hop count travels.** Every ``crm.record.event_occurred`` payload
carries the ``correlation_id`` and ``depth`` it was enqueued with (decided at
*enqueue* time — see ``shared.service._enqueue_record_event``). The engine
reads them off the event and, only while running that rule's actions, sets
this module's context variable to ``depth + 1``. Any write those actions
cause enqueues its own event at that incremented depth, carrying the same
``correlation_id`` — so every event in one causal chain shares an id an
operator can filter execution history by, and the chain cannot loop past
:data:`MAX_WORKFLOW_CHAIN_DEPTH` hops from the original, human-initiated write
(depth 0, no context set at all).

A write made outside any workflow action sees no context (``current() is
None``) and starts a fresh chain: a new ``correlation_id``, depth 0.
"""

from __future__ import annotations

import contextlib
import dataclasses
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Final

#: Hops permitted from the original write before further automation is
#: suppressed. The write itself always succeeds; only the *next* event this
#: chain would enqueue is dropped once depth would exceed this. Five is deep
#: enough for a deliberate multi-step process (status -> task -> notify -> ...)
#: and shallow enough that a two-workflow cycle stops within a fraction of a
#: second rather than consuming the worker.
MAX_WORKFLOW_CHAIN_DEPTH: Final = 5


@dataclasses.dataclass(frozen=True, slots=True)
class WorkflowExecutionContext:
    """The chain identity and depth to stamp on any event enqueued right now."""

    correlation_id: uuid.UUID
    depth: int


_current: ContextVar[WorkflowExecutionContext | None] = ContextVar(
    "crm_workflow_execution_context", default=None
)


def current_workflow_context() -> WorkflowExecutionContext | None:
    """The context a write is happening under, or ``None`` for a fresh chain."""
    return _current.get()


@contextlib.contextmanager
def workflow_execution_scope(context: WorkflowExecutionContext) -> Iterator[None]:
    """Mark every write made inside this block as caused by ``context``.

    Used only around action execution (`.service._run_rule`) — never around
    the trigger lookup or condition evaluation, which read but do not write.
    """
    token = _current.set(context)
    try:
        yield
    finally:
        _current.reset(token)


__all__ = [
    "MAX_WORKFLOW_CHAIN_DEPTH",
    "WorkflowExecutionContext",
    "current_workflow_context",
    "workflow_execution_scope",
]
