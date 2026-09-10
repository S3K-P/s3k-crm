"""Authorization for saved views (ADR-010).

Two dimensions, and they are not the same question:

* **May you read this view?** Decided by the view's own ``visibility`` —
  private to its owner, shared with their team, or organization-wide — and
  expressed as a SQL predicate in :mod:`.repository`, so it is applied at the
  single point views are queried rather than filtered in Python afterwards.
* **May you change it?** Its owner always may. Anyone else needs
  ``views.VIEW_ALL``, the same grant that lets a manager see across owners
  elsewhere in the product. Enforced in :mod:`.service`.

Neither dimension grants sight of a single record. A view names filters over a
module; running it goes through that module's own endpoint, behind that
module's permission and record-level visibility. So a rep who is shown a
manager's "All open deals" view still sees only the deals they may see, and a
caller holding ``views.VIEW`` but not ``opportunities.VIEW`` gets 403 the
moment they try to use it.
"""
