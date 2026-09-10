"""Authorization for the calendar (ADR-010).

The calendar declares no permission of its own, and that is the design rather
than an omission. It shows meetings and tasks; a person's right to see either
is decided by ``activities.VIEW`` and ``tasks.VIEW`` and by the record-level
visibility those modules already apply. Inventing a ``calendar.VIEW`` would
create a grant that either duplicates those two or — far worse — could be held
without them and become a way to read records around their own permission.

So the route is mounted behind authentication and the CRM product gate, and
:class:`~app.products.crm.calendar.service.CalendarService` consults the
caller's permissions per source. A caller entitled to one and not the other
gets the half they may see rather than a 403, because a rep with no activity
access still has a calendar of their own tasks and refusing it outright would
be the wrong answer to a legitimate request.
"""
