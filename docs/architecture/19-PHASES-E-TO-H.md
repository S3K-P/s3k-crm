# Phases E–H — what was built, and the decisions behind it

Written 2026-09-13, verified against the repository. Follows Phase D
(`55e86f4`, user-authored email). Four phases in one run:

| Phase | Subject | Commit |
|---|---|---|
| E | Custom fields, picklists, permissions | `d406d96` |
| F | Saved views, calendar, merge, data model | `1826541` |
| G | Blueprints | `e1be333` |
| H | QA, the transaction fix, indexes | this document's commit |

This is a record of the decisions, not a tutorial. Each section says what was
built, what was rejected, and what the reader should be careful of.

---

## Phase E — custom fields and picklists

### Where a custom value lives

A single `custom_fields` JSONB column on each of the five record types, not an
entity-attribute-value table. Three reasons, in order of weight:

1. **No N+1, ever.** A record's custom values arrive with the record, in the
   row the list query already selected. EAV needs a second query per page — or
   a join whose row multiplication has to be collapsed again — on every list
   screen in the product.
2. **Retiring an option cannot corrupt a record.** A stored value is a string,
   not a foreign key. Under EAV, removing an option is either blocked or
   cascades into stored data; both are worse than a value that keeps rendering.
3. **One migration.** Adding a field is data. Nothing in the schema changes
   when an administrator defines their fortieth field.

The cost is that a JSONB value has no type to compare against. That is paid in
`custom_fields/filters.py`, which chooses the cast from the *definition's*
declared type — never from anything in the request — and guards every numeric
and temporal cast with a regex inside a `CASE`, so one malformed document
cannot fail a whole list query for everybody.

### The rule that makes it safe to retire things

- An **inactive definition** is not rendered, required or validated. Values
  already stored under it are kept and still returned.
- An **inactive option** cannot be newly selected, but a record already holding
  it keeps it — *including through an edit of an unrelated field on that
  record*. This is the case a naive implementation gets wrong: re-validating
  the whole document against the live option set on every write silently strips
  a colleague's historical value the first time anybody touches the record.

### Where validation happens, and why there

Inside `TenantScopedService`, the funnel every CRM entity write already passes
through. Reached by a registry inversion (`shared/custom_field_hook.py`),
because `crm/shared` sits below the modules and may not import `custom_fields`,
which subclasses it — the same inversion attachments' record access and the
reminder source already use. **Unregistered means refused, not permitted**, so a
misassembled application cannot quietly skip the check.

The practical effect: a record type added next year cannot ship a write path
that stores an unvalidated custom value, because there is no per-module call to
forget.

### Permissions

`custom_fields.VIEW` is granted to **every** system role, which is unusual and
deliberate. A rep who cannot see that leads have a Region field gets a form
missing half its inputs. It grants sight of the tenant's configuration only — a
record's *values* stay behind that record's own module permission and
record-level visibility.

---

## Phase F — views, calendar, merge

### Saved views

A view stores a **question, never an answer**: filters, sort, columns, and no
rows. Consequences: one opened a year later shows that day's records, and two
colleagues opening one shared view legitimately see different rows, because
running it goes through the record type's own endpoint behind that module's
permission.

`views.VIEW` therefore reaches no record at all. Editing somebody else's view
needs `views.VIEW_ALL` — reusing the manager grant rather than inventing a
`views.MANAGE` nobody would think to hand out. A colleague's private view is a
**404, not a 403**, so the error cannot confirm it exists.

### Calendar

A read model over meetings and tasks. It owns no table and declares no
permission: a `calendar.VIEW` would either duplicate `activities.VIEW` and
`tasks.VIEW` or, held without them, be a way around them. Each half is
authorized on its own terms, so a caller entitled to one gets that one rather
than a 403.

**Timezones are the whole difficulty and the rule is absolute.** Every instant
crosses the wire with an offset, in both directions. There is no date parameter
anywhere, because a date has no instant without a zone and a server picking one
puts a +14:00 user's Monday meetings on Sunday — silently, in a way that looks
like missing data.

Two bugs found while building it:

- `crm.meetings` had **no index on `start_time`**. Every grid render would have
  scanned the tenant's whole meeting history.
- A `+` in a query string decodes as a **space**, which silently naive-ised
  every positive offset. The window now repairs it (a space in that position is
  never valid ISO-8601, so the repair is unambiguous) and still refuses a
  genuinely naive value.

The companion index on `crm.tasks(organization_id, due_date)` was **checked, not
assumed** — revision `8224845a67ac` already built it, and a duplicate would cost
write throughput on every task and buy nothing.

### Merge

The operation with the most to lose, so the design is arranged so its mistakes
cannot happen:

- **Nothing is lost.** Every reference moves to the survivor before the losers
  are retired — activities, tasks, notes, mail, files, campaign memberships and
  every foreign key that named them.
- **The losers keep a `merged_into_id`**, so a stale bookmark or an
  integration's stored id still resolves to where the data went. "Deleted" and
  "became part of that one" are different facts.
- **One transaction.** A failure leaves nothing moved and nothing retired — the
  alternative is a duplicate pair that is now worse than before.
- **`FOR UPDATE` in id order**, so two admins working the same duplicate report
  queue rather than corrupt each other.
- **Field choices name a *source*, never a value.** A client that could post
  values could write anything into the record under cover of a merge, bypassing
  the rules that record's own PATCH endpoint enforces.
- **`EDIT` *and* `DELETE`**, because a merge is both.

The references a merge moves are a **declared catalogue**, not reflection over
foreign keys. Reflection cannot see the polymorphic `related_entity_*` links —
which is where most of a record's history hangs — and would silently start
rewriting a column somebody adds next year. A list that must be edited when a
reference is added is one that gets *reviewed* when a reference is added.

Opportunities and campaigns are deliberately **not** mergeable: two deals
against one account are usually two deals, and merging them would destroy the
stage history the pipeline report is computed from.

---

## Phase G — blueprints

A blueprint is a tenant's own process over a state field a record already has.

### The one property everything follows from

**A blueprint narrows what the product allows and can never widen it.** The
built-in state machine runs first, the blueprint second. Without that ordering
an administrator could configure their way past rules the rest of the system
depends on — that a lead reaches `CONVERTED` only through conversion, so an
account exists; that a closed deal stays closed. The failure would surface far
from its cause, as a `CONVERTED` lead with nothing behind it.

The configuration API therefore refuses a rule for a move the machine would not
allow anyway: such a rule could never fire, and its author would reasonably
believe they had enabled something.

### The compatibility rule

**A half-described process is not a wall.** A blueprint constrains a destination
state only once it has an opinion about that state, and then constrains it
completely. Without this, activating a partial blueprint would freeze every
record not already covered by it. This is the roadmap's "existing records remain
compatible" requirement, expressed as a rule rather than a migration.

### What cannot be configured

Server-side, at write time and again at activation:

- a state must exist — an enum member, or a live pipeline stage in this tenant;
- a required field must be a real column or a live custom field, or the rule
  can never be satisfied;
- a required permission must be in the catalogue, or nobody can satisfy it;
- at most one **active** blueprint per field (two would permit and refuse the
  same move, with row order deciding);
- one rule per origin/destination pair.

The last two are enforced by partial unique indexes as well, so a path that
bypassed the service still cannot create one.

`from_state` uses the literal `'*'` rather than NULL for "from anywhere",
because NULL is not equal to NULL in a unique index and a nullable column would
let an administrator create the same wildcard rule twice.

---

## Phase H — the transaction fix

### The defect

FastAPI keeps **two exit stacks** per request. A dependency with `yield` lands
on the *request* stack by default, which is closed after
`await response(scope, receive, send)` — after the response bytes have gone to
the client.

The session dependency's `COMMIT` therefore ran **after the caller had already
been told the write succeeded**. A client reading back immediately could race
it and observe the state from before its own write. The window is small, it
widens under load, and it reads as "the UI sometimes doesn't refresh".

### The fix

`app/core/database.py`:

```python
DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
```

`scope="function"` puts the session on the stack FastAPI drains **before**
sending the response. This is the central fix the situation called for — it
changes *when* the commit happens in the request lifecycle, not what commits,
and it removes the problem rather than working around it at any call site.

Two consequences, both improvements:

- A background task must not use this session. It is closed by the time one
  runs, which is correct: a task that needs the database should open its own,
  as the ARQ worker already does. (The application registers none today.)
- An error while committing now surfaces as a 500 instead of being logged after
  a success was already reported. A failed commit *is* a failed request, and
  telling the caller otherwise was the more serious of the two bugs.

### Why it is pinned by a test

`tests/integration/test_read_after_write.py` asserts both the property (write,
then read, repeatedly) and the **mechanism** (`DbSession` declares
`scope="function"`, and FastAPI's default is still the late stack).

The property alone is not enough: it is timing-dependent enough to pass by luck
on a fast machine, and a future FastAPI upgrade that changed the default would
flip the mechanism silently while the timing test stayed green for months.

---

## Phase H — a second stale-answer bug, found by the end-to-end suite

`visibility.spec.ts` failed on a sign-in that had visibly succeeded. The API log
said why, to the second:

```
18:33:29  logout
18:33:30  refresh_token_reuse_detected     (request df782289)
18:33:31  login_succeeded                  (the next person)
18:33:32  401 /auth/refresh                (request df782289, still unwinding)
```

Signing out revokes the refresh cookie. The next page load probes that cookie to
find out who is signed in — and the login form is **not** behind `RequireAuth`,
so the next person can sign in while that probe is still on the wire. The probe
is then refused, correctly, and answers "nobody is signed in". That answer is
true of the session that just ended and false of the one that replaced it, and
`AuthContext`'s restore effect acted on it: `clearSession()`, then a redirect
to the login form. The person watched their own sign-in succeed and was bounced
out of it a second later, with nothing on screen to explain why.

**The fix** is a session *generation* (`lib/api-client.ts`): a counter bumped by
every deliberate transition — sign-in, sign-up, sign-out — and never by a
refresh, because a rotation replaces a token without replacing the session.
Anything that awaits an answer about the session captures the generation first
and compares it after; if it moved, the answer is about a session that no longer
exists and is dropped. Two places consult it:

- the restore effect in `AuthContext`, which is the path reproduced above;
- the 401 branch of `sendAuthenticated`, where a request that outlived its own
  session could end the next one the same way. The request still fails, because
  it did — it just fails alone.

`cancelled` could not have covered either case. It suppresses a state update
after an *unmount*, and nothing unmounts here: the provider lives in the root
layout and outlives every sign-in the tab performs.

**It is not pinned by a test, and that is worth stating plainly.** The failure
was seen once, with the log above and a screenshot of the login form. Three
later runs of the same spec against a build *without* the guard passed, and two
deliberate reproductions — holding a request's refresh, then holding the page
load's probe — passed with the guard removed as well: the restore effect re-runs
after a sign-in and cancels the older attempt, which closes the window in the
arrangements a test can construct. A test that passes either way is worse than
no test, so neither was kept.

What remains is a guard that is cheap, provably harmless (every suite passes
with it), and correct on its own terms: acting on an answer about a session that
has since been replaced is wrong whatever the timing that produced it. It is a
defence reasoned from one captured failure, not a fix demonstrated against a
reproduction, and a future reader deciding whether to keep it should know which
of those it is.


## Data model review

A scan of `pg_constraint` reports twenty-three foreign keys with no index
leading on their column. **Nineteen of them were left alone**, and that is the
finding rather than an omission.

The application filters by `organization_id` first in every query it makes, and
the composite `(organization_id, <column>)` indexes that already exist serve
those. An index per foreign key would cost write throughput on every insert and
update, forever, to serve referential-integrity checks on a parent delete that
this product never performs — deletion is soft everywhere.

Four were added (`20260913_0100`), each justified by a query that exists:
`MergeService._repoint` filters on them and had nothing to match its shape.
Partial on `IS NOT NULL`, because most accounts name no primary contact and most
leads were never converted.

**Deployment note.** `CREATE INDEX` takes a brief `SHARE` lock. For a large
existing deployment, create those four with `CREATE INDEX CONCURRENTLY` outside
the migration and stamp the revision — Alembic cannot run it inside
transactional DDL.

---

## Things a future reader should be careful of

1. **`scope="function"` on `DbSession` is load-bearing and invisible.** It is
   one keyword argument with no visible effect in development. The test above
   is the only thing that would notice its removal.
2. **The merge catalogue must be edited when a reference is added.** A new
   column pointing at an account, or a new table with `related_entity_*`, is
   not discovered automatically — by design.
3. **A blueprint can only narrow.** If a future requirement is "let an
   administrator enable a move the product forbids", that is a change to the
   built-in state machine, not to blueprints.
4. **Custom field `api_name` and `field_type` are immutable after creation.**
   Stored values are keyed by the first and read through the second. The
   supported way to change a field's meaning is to deactivate it and add
   another, which keeps the collected data legible.
5. **The calendar takes instants, never dates.** Any future endpoint that
   accepts a day boundary should do the same.
6. **`setAccessToken` bumps the session generation, and callers depend on it.**
   Anything that awaits an answer about the session must capture
   `currentSessionGeneration()` first and drop the answer if it moved. A new
   async path that clears the session without that check reintroduces the
   sign-in-undone bug above.
7. **`FormField` wraps its label around the control**, so a `<select>` inside
   one is named "label text" + "selected option text" — "To" announces as
   "ToChoose…". The blueprint transition selects carry an explicit `aria-label`
   for that reason. Any other select behind a short label wants the same, and
   the general fix is to associate by id instead of by nesting.
