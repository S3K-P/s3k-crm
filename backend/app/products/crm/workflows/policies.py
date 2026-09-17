"""Authorization for workflow automation (ADR-010).

Two distinct questions, the same split ``blueprints.policies`` makes and for
the same reason:

* **Configuring a rule** needs ``workflows.CREATE`` / ``EDIT`` / ``DELETE``,
  which only Admin holds by default. A workflow decides what happens to
  everybody else's records when something changes — creating tasks in their
  name, moving stages, sending mail as the organization — which is
  administration in the strongest sense the product has, stronger than
  editing any single record.
* **Reading the execution history** needs ``workflows.VIEW``, granted to
  every system role. A rep whose deal unexpectedly got a follow-up task or an
  email has to be able to see *why* — which rule fired, what it did, whether
  it failed — and hiding that turns an automated action into a mystery.

A workflow's actions are never a second, weaker-gated write path: every one
of them calls the entity's own service, the one a human request would call —
see ``.actions``'s module docstring for exactly what authorization semantics
a system-initiated action does and does not carry, since there is no user to
check a permission against.
"""
