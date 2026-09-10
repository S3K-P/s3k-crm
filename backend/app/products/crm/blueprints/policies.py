"""Authorization for blueprints (ADR-010).

Two distinct questions, and conflating them would be the mistake:

* **Configuring a process** needs ``blueprints.CREATE`` / ``EDIT`` / ``DELETE``,
  which only Admin holds by default. A blueprint decides what everybody else in
  the organization may do with a record, so writing one is administration in
  the strongest sense the product has — stronger, in effect, than editing any
  single record.
* **Reading a process** needs ``blueprints.VIEW``, granted to every system role.
  A rep whose transition was refused has to be able to see why and what would
  unblock it; hiding the rule that stopped them turns a clear 422 into a
  mystery. It grants sight of the configuration and of no record at all.

A blueprint is *applied* on the lead and opportunity state-change paths, behind
those modules' own permissions, so ``blueprints.VIEW`` is never a way to reach
a record. And a transition's ``required_permission`` is an **additional**
demand checked on top of the endpoint's own — it can only ever narrow who may
make a move, never grant somebody a move they could not otherwise make.
"""
