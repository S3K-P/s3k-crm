"""Building blocks shared by every CRM module.

``pagination``  the list envelope, page parameters and sorting contract
``repository``  the generic organization-filtered repository
``service``     the generic tenant-scoped CRUD service

These exist so that tenant scoping is implemented once and cannot be forgotten
by an individual module.
"""
