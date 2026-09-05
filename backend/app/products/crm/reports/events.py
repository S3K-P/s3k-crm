"""Domain events for the reports module (ADR-013).

Deliberately empty. Running a report reads and changes nothing, so there is
no state transition for another module to consume — the same reason the audit
module publishes none of its own.

Running one is also, deliberately, **not audited**. The trail records actions
that change data or take it out of the application's reach: a create, an
ownership change, an export, an attachment download. A report is a read of
records the caller could already open one at a time, through screens that log
nothing per view; an entry per run would fill the trail with the least
interesting thing in it and bury the entries that matter.

An **export** of a report is a different act, and would be audited as one
alongside ``RECORDS_EXPORTED``, when that route exists.
"""
