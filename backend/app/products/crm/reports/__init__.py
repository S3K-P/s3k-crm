"""S3K CRM module: reports.

The built-in report library, and the one call that runs an entry in it.

    catalog.py     what reports exist; one table, nine rows
    repository.py  the grouped queries, each taking a RecordVisibility
    service.py     resolve, authorize, scope, run, resolve names
    policies.py    why there is no `reports` permission module
    schemas.py     the self-describing result envelope
    router.py      GET /crm/reports and POST /crm/reports/{key}/run
    models.py      why the catalogue is code rather than seeded rows
    events.py      why running a report is neither published nor audited

A report here is reviewed code with parameters, not user-authored SQL. The
custom builder Zoho offers is a later, constrained addition on top of this
shape rather than a different one — see the note at the top of `catalog.py`.
"""
