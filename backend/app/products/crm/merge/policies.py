"""Authorization for merging (ADR-010).

Merging declares no permission module of its own, deliberately. It is not a
capability separate from the records it acts on — it is an edit and a deletion,
performed together — so it is authorized against the record's own module and
needs **both**:

* ``<module>.EDIT``, because the surviving record changes; and
* ``<module>.DELETE``, because the others are retired.

Requiring both is the point. A ``merge`` permission of its own would be a third
grant an administrator could hand out without realising it lets somebody remove
records they were deliberately not given ``DELETE`` for. The check is in
``router.py`` rather than a route dependency because the module is a path
parameter and is not known when the route is declared — the same reason imports
and reports authorize inside their handlers.

Record-level visibility applies on top: every record in a merge is resolved
through ``RecordVisibility.for_module``, so a rep cannot merge a colleague's
lead into their own, and a record from another tenant is a 404 rather than a
403 — indistinguishable from one that does not exist.

Previewing needs only ``<module>.VIEW``. It reads and writes nothing, so a rep
can see what a merge would do and hand it to somebody who may perform it.
"""
