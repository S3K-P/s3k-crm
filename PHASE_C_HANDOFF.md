# Phase C (Event Spine) — Handoff

Written 2026-09-08, verified against the repository. Worktree
`.claude/worktrees/phase-b-reports`, branch `phase-c-event-spine`, HEAD
`86a2d77`. Nothing is committed; the whole of the work below is in the working
tree.

## 1. Objective

Give the product a real asynchronous spine so the things it promises actually
happen: a transactional outbox, an ARQ worker draining it with retries and a
dead-letter state, a pluggable email provider, real delivery of invitation /
password-reset / meeting-reminder mail, and the ability to run more than one
API replica.

Acceptance list, in order:

> transactional outbox → ARQ worker → retries/DLQ → email provider →
> invitation/password-reset/reminder delivery → scheduled jobs →
> email delivery log → horizontal-scaling validation

Gate: **do not start Phase D/E/F/G** until every item passes and the full
regression suite is green.

## 2. Completed

### Committed (3 commits, not pushed)

| Item | Where | Verified by |
|---|---|---|
| Phase A cherry-picked onto this trunk (in-app notifications, reminder scheduler) | `7618993` | `test_notifications.py` |
| Alembic history un-branched (notifications migration `20260904_0100` → `20260906_0100`) | `7618993` | `alembic upgrade head` from zero |
| Per-address login/signup throttle (`X-Forwarded-For` counted from the right) | `bf8fb7d`, `app/core/rate_limit.py`, `app/platform/auth/throttle.py` | 16 unit + 9 integration |
| Playwright suite (11 specs, self-seeding, incl. record visibility) | `bf8fb7d`, `frontend/e2e/` | `npm run test:e2e` |
| Transactional outbox (`FOR UPDATE SKIP LOCKED`, stall reclaim) | `86a2d77`, `app/platform/events/` | `test_outbox.py` |
| ARQ worker + cron drain | `86a2d77`, `app/worker.py`, `backend/scripts/worker.sh` | `test_outbox.py` |
| Retries, exponential backoff + jitter, dead-letter status | `86a2d77`, `app/platform/events/service.py` | `test_outbox.py` |
| Email provider (SMTP / console / null — since replaced by Microsoft Graph / console / null) | `86a2d77`, `app/platform/email/provider.py` | `test_email_delivery.py` |
| **Invitation** delivery | `86a2d77`, `organizations/router.py::_request_invitation_email` | `test_email_delivery.py` |
| Scheduled jobs (reminder poller API → worker; `notifications_scheduler_enabled` defaults `False`) | `86a2d77` | `test_horizontal_scaling.py` |
| Horizontal scaling (`numReplicas` 1 → 2; `pg_advisory_xact_lock` in `migrations/env.py`) | `86a2d77`, `app/core/database.py::MIGRATION_LOCK_KEY` | `test_horizontal_scaling.py` |

### Uncommitted in the working tree — feature-complete and green

**Password-reset delivery.** This turned out to mean *building the
self-service reset flow*, which did not exist (only `PASSWORD_RESET_BY_ADMIN`).
`platform.password_reset_tokens` (SHA-256 digest, `used_at`, TTL),
`AuthService.request_password_reset` / `redeem_password_reset`,
`POST /auth/forgot-password` (always 202, throttled) and
`POST /auth/reset-password`, audit actions `PASSWORD_RESET_REQUESTED` /
`PASSWORD_RESET_COMPLETED`, setting `password_reset_ttl_seconds`, migration
`20260908_0100`, and the `/forgot-password` + `/reset-password` screens with
`components/platform/AuthCard.tsx` and a link on `/login`.

**Email delivery log.** `app/platform/email/{repository,schemas,router}.py`
mounted at `/api/v1/email-deliveries` behind `audit.VIEW`, plus
`app/(crm)/admin/email-deliveries/page.tsx`,
`features/admin/email-deliveries/index.ts` and the nav entry.

**Meeting-reminder email.** The template existed but nothing sent it.
`ReminderDue` gained `email_template` / `email_context` / `record_path`; CRM
meeting reminders opt in, task reminders deliberately do not;
`NotificationService._request_reminder_email` enqueues inside the scheduler's
transaction.

**Empty-body successes in the API client.** `apiRequest` parsed JSON on every
non-204 success, which broke `/forgot-password` outright — see §3. One file,
`frontend/lib/api-client.ts`; it is the 23rd modified path and the only change
made after the full backend suite was run.

### The 7 previously-failing tests — all fixed and green

Neither was an application defect. Both were wrong assumptions in tests
written in the same session, and both are worth remembering because the
mistakes are easy to repeat:

1. **Six `KeyError: 'total'`.** The list envelope is
   `{"data": [...], "pagination": {"total": N}}` — `app/core/pagination.py::Page`
   — not `{"items", "total"}`. The endpoint was returning correct data
   throughout.
2. **`assert 2 == 1` in the reminder-email test.** `clean_database` clears
   tenant business tables; `platform.outbox_events` is Platform
   infrastructure and is not among them. So `EventDispatcher.drain_once()` in
   one test delivers events enqueued by earlier tests in the same file, which
   looks exactly like a duplicate send. `reminder_mailbox` in
   `test_notifications.py` now wipes the table on both sides of the yield.
   **Any future test that drains the outbox needs the same.**

### New E2E coverage — `frontend/e2e/password-reset.spec.ts`

8 tests. Typechecked, lint-clean, and **run — 8/8 green** (see §3).

Covers: the flow is reachable from the sign-in form; the confirmation screen
is byte-identical for a registered and an unregistered address; a missing
token and a rejected token each fail on the screen that says so; the password
is not left in the form after a rejection; every dead end returns to sign-in.

It deliberately does **not** redeem a real token. The token exists only in the
email — the delivery log stores no body, precisely so a bearer credential is
not sitting where an administrator can read it — so no browser can obtain one.
Redemption is covered by the 16 tests in
`backend/tests/integration/test_password_reset.py`.

## 3. Verification status

Verified:

- `test_email_delivery_log.py` + `test_notifications.py` — **22 pass**
- `test_email_delivery.py` + `test_outbox.py` + `test_password_reset.py` — **41 pass**
- `test_crm_rls.py` — 20 pass, incl. the new `email_deliveries` optional-tenant
  assertion against the live catalogue
- Unit suite — 698 pass, incl. 9 new `test_schema_audit.py` optional-tenant cases
- `ruff check app tests migrations` — clean
- `mypy app` (241 files) — clean
- Frontend `npx tsc --noEmit` — clean
- Frontend `npm run lint` (eslint) — clean
- Migration `20260908_0100` applies; policy confirmed in `pg_policy` as
  `NOT (organization_id IS DISTINCT FROM ...)`
- **Full backend suite over the working tree — exit 0, clean.** Completed
  2026-09-08 after this file was first written; log
  `…/scratchpad/full-suite-2.log` ends `[100%]` with `EXIT=0`. This is the
  verdict that was pending, and it covers every uncommitted change listed
  above.

- **`password-reset.spec.ts` — 8/8 green.** Run 2026-09-08 against the E2E
  stack of §5, with `PLAYWRIGHT_CHANNEL=chrome`: the Playwright browser CDN is
  unreachable from this machine (`npx playwright install chromium` fails on TLS
  timeouts and leaves the cache empty), so the locally installed Chrome is not
  optional here. The full suite was also run — the other 11 specs are covered
  below.

**Nothing in Phase C is now unverified.** The first run of the spec found one
real defect and two of its own, all three fixed:

1. **`frontend/lib/api-client.ts` — application defect, fixed.** `apiRequest`
   special-cased only 204 before calling `response.json()`.
   `POST /auth/forgot-password` answers **202 with an empty body** by design,
   so `.json()` threw a `SyntaxError` — not an `ApiError` — and
   `/forgot-password` fell through to its generic
   "Unable to send a reset link right now." **Every successful reset request
   was reported to the user as an outage**, while the backend logged
   `password_reset_requested` and returned 202. The integration tests could not
   see this: they assert on the 202 itself. It now reads the body and parses
   only if there is one. This is the whole reason the E2E gate existed.
2. `getByLabel('New password')` matched `Confirm new password` too —
   `getByLabel` is a substring match — so three tests died on strict mode.
   Now `{ exact: true }`.
3. `getByRole('alert')` also matched Next's route announcer, which made two
   tests pass or fail on mount order. Now scoped to the form.

Assertions were not weakened; only the locators changed.

**Pre-existing flake, not Phase C, not fixed (out of scope):** the 11 older
specs fail intermittently — a different subset each run — and pass in
isolation. `auth.spec.ts:34`, `crm-journey.spec.ts:14` and
`visibility.spec.ts:57` are the ones seen. Cause is identified with evidence:
`frontend/context/AuthContext.tsx:130` POSTs `/auth/refresh` on mount **without**
the `refreshInFlight` guard that `api-client.ts:78` uses, so under React
StrictMode's dev double-mount two requests carry the same rotating cookie. The
backend correctly reads that as a replay and revokes the family
(`refresh_token_reuse_detected`, logged in pairs sharing a `family_id`, several
with `sessions_revoked=2`). `AuthContext.tsx` is untouched by Phase C, and a
run of the three older specs *without* `password-reset.spec.ts` still failed
one — this predates and is independent of the work here. Needs its own fix;
do not change the backend replay detection, which is behaving as designed.

## 4. Two corrections to the state as dictated

- **`.claude/launch.json` has NOT been modified.** `git diff` on it is empty.
  The entries for `e2e-backend` (8100) and `e2e-frontend` (3100) exist only as
  an unapplied script at
  `…/scratchpad/add_launch_entries.js`. If it is run, the file is tracked and
  the change must be reverted before committing.
- **`password-reset.spec.ts` is untracked, not `git add`-ed.** Nothing in this
  work has been staged; `git status` shows 22 modified and 13 untracked paths.

## 5. Environment prepared for the E2E run

- `s3k_e2e_run` migrated to `20260908_0100` (separate database from
  `s3k_reports`, which the backend suite is using).
- `frontend/.env.local` → `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8100`.
  Git-ignored (`.gitignore:41`), delete after the run.
- `…/scratchpad/e2e.env` holds the backend overrides: the `s3k_e2e_run` URL,
  `CORS_ALLOWED_ORIGINS` for `:3100`, `LOGIN_RATE_LIMIT_ATTEMPTS=500`,
  `TRUSTED_PROXY_HOPS=0`, `PUBLIC_APP_URL=http://127.0.0.1:3100`,
  `NOTIFICATIONS_SCHEDULER_ENABLED=false`, `EMAIL_PROVIDER=null`. Loaded with
  `uv run --env-file <path>`; real env vars take precedence over `backend/.env`.
- `LOGIN_RATE_LIMIT_ATTEMPTS=500` is not optional: `/auth/forgot-password`
  shares the login throttle bucket, and the whole E2E suite runs from one
  address.
- Prior seed at `frontend/.playwright/seed.json` is stale; `global-setup.ts`
  reseeds.

## 6. Decisions that affect continuing

1. **Two email event types.** `EMAIL_REQUESTED` is `tenant_scoped=True`;
   `IDENTITY_EMAIL_REQUESTED` (password reset only) is `tenant_scoped=False`.
   `request_email` picks by whether `organization_id` is `None`. Collapsing
   them would mean registering the shared handler untenanted, so a future bug
   dropping the org from an invitation would deliver unscoped instead of
   dead-lettering.
2. **`email_deliveries.organization_id` is nullable with a NULL-aware policy.**
   A reset is addressed to a global identity (a user may belong to several
   organizations, or — after signup, before onboarding — to none), but the row
   must exist because the unique index on `outbox_event_id` is the whole
   exactly-once guarantee. `IS NOT DISTINCT FROM`, so untenanted rows are
   visible only to an unscoped session and to no tenant.
3. **The schema audit learned that shape rather than being excused from it.**
   `audit_tenant_isolation(..., optional_tenant={...})` swaps the "nullable
   column" finding for a stricter one: the policy *must* be NULL-aware.
   `pg_get_expr` renders `IS NOT DISTINCT FROM` as `NOT (x IS DISTINCT FROM y)`;
   both spellings are accepted, a bare `IS DISTINCT FROM` is rejected as the
   inverted policy.
4. **The delivery log reuses `audit.VIEW`** rather than adding a permission
   module, which would need a migration, a role-template decision and a
   frontend matrix entry to gate one read-only screen.
5. **Reset issues no session.** The user signs in with the new password, which
   is what proves it took.
6. **Meeting reminders are emailed; task reminders are not.** Opt-in per
   reminder via `ReminderDue.email_template`.
7. **The integration suite raises the login-throttle allowance**
   (`SUITE_LOGIN_ATTEMPT_ALLOWANCE = 5000`, `tests/integration/conftest.py`)
   because every `as_*` fixture signs in from one address;
   `test_login_throttle.py` narrows it back to `THROTTLE_LIMIT = 8`. This was
   the cause of the earlier full-suite failures.

## 7. Known issues

Pre-existing, out of scope, already flagged separately: `POST /crm/activities`
with a `meeting` omitting `meeting_type` returns 500 — `exclude_unset=True`
drops the schema default and the column is NOT NULL.

## 8. Exact next steps

1. ~~Full backend suite~~ — **done, exit 0** (§3). Still valid: the only change
   made since is `frontend/lib/api-client.ts`. No Python was touched — the
   backend still shows exactly the 19 modified files it did then — so the
   verdict stands and re-running it proves nothing.
2. ~~Start the E2E stack~~ — **done**. Note `.claude/launch.json` is resolved
   from the *session's* working directory, which may be a different worktree
   than this one; entries can point here by absolute path
   (`uv run --directory <abs>/backend …`, `npm run dev --prefix <abs>/frontend`).
3. ~~Run `password-reset.spec.ts`~~ — **done, 8/8** (§3).
4. ~~Fix genuine application failures~~ — **done**: one, in
   `frontend/lib/api-client.ts` (§3).
5. ~~Re-run what the fixes touched~~ — **done**: frontend `tsc --noEmit` clean,
   `eslint` clean, full Playwright suite run twice, `password-reset.spec.ts`
   8/8 in isolation.
6. ~~Review `git status` and `git diff`~~ — **done**. 23 modified (the 22 of §4
   plus `frontend/lib/api-client.ts`) and 13 untracked; nothing staged.
7. ~~Revert `.claude/launch.json`~~ — **done**. `frontend/.env.local` is still
   present and still git-ignored; delete it before running a non-E2E dev
   server, which would otherwise talk to :8100.
8. Commit the Phase C work as one commit on `phase-c-event-spine`, push, open a
   PR against `s3k/main`. Suggested subject:
   `feat(platform): self-service password reset, reminder email and a delivery log`
   The body should carry §6.
9. **Do NOT begin Phase D.**

---

## NEW SESSION START

Read this file first. Then:

1. `git status` and `git log --oneline -3` — expect branch
   `phase-c-event-spine`, HEAD `86a2d77`, **23** modified and 13 untracked
   paths, nothing staged, `.claude/launch.json` unmodified.
2. The full backend suite is **already green over this working tree** (exit 0,
   §3). Do not re-run it unless you change Python.
3. **Phase C is verified in full — there is nothing left to check** (§3). The
   only remaining step is §8 step 8: commit, push, open the PR.
4. Two things found here that are deliberately *not* Phase C's to fix: the
   `/auth/refresh` double-call that revokes session families (§3), and the
   pre-existing `POST /crm/activities` 500 (§7).

Do not start Phase D.
