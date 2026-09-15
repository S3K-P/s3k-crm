# S3K CRM — CRM Modernization Progress

A living handoff file. Every status below was checked against the code on this
branch, not the UI's appearance. Update it at the end of each checkpoint.

## Current Branch

`claude/crm-zoho-gaps` — created from `s3k/main` (remote `s3k` =
`https://github.com/S3K-P/s3k-crm.git`, the canonical repository).

> The remote `origin` (`khushijwadhwa18/S3K_CRM`) and the local `main` branch
> are the old prototype line. Never base work on them.
>
> This branch tracks `s3k/main`. Push it with an explicit name:
> `git push -u s3k claude/crm-zoho-gaps`. A bare `git push` would aim at `main`.

## Base Commit

`9ed50eb` — *Merge pull request #11 from S3K-P/claude/s3k-crm-phases-e-h-c22ed1*.

## Existing Phase E-H Work

Already on `main`; treat all of it as existing functionality. Design record:
[`docs/architecture/19-PHASES-E-TO-H.md`](architecture/19-PHASES-E-TO-H.md).

| Phase | Commit | What exists |
|---|---|---|
| D (predecessor) | `55e86f4` | User-written email: compose, templates, threads, outbox delivery |
| E | `d406d96` | Custom fields (12 types, validation, defaults, required), reusable picklists, `custom_fields.*` permissions |
| F | `1826541` | Saved views (filters/sort/columns, private/shared), calendar (meetings + tasks), record merge (accounts, contacts, leads) |
| G | `e1be333` | Blueprints — tenant processes over lead status and opportunity stage, enforced server-side |
| H | `22cd476` | Commit-before-response fix (`DbSession scope="function"`), session-generation guard, merge-reference indexes (`20260913_0100`) |

All nine items the audit was asked to confirm exist: custom fields ✅,
picklists ✅, permissions ✅, saved views ✅, calendar ✅, record merge ✅,
blueprints ✅, QA/reliability work ✅, DB indexes/performance work ✅.

## Audit Date

2026-09-11

---

## Executive Summary

**75 features audited: 57 ✅ COMPLETE · 17 🟡 PARTIAL · 1 🔴 MISSING** (Checkpoint 2 moved primary contacts to complete and Kanban drag-and-drop from missing to partial; Checkpoint 3 wired the Leads board to move Kanban drag-and-drop to complete, and substantially extended Activities, Tasks, Timeline, Files and Email without changing their own status; Checkpoint 4 built the form/layout builder, conditional fields, inline and bulk editing, moving items 31–36, 47 and 48 to complete and 41 from missing to partial; Checkpoint 5 built the ad-hoc report builder, a multi-condition AND/OR filter engine, and dashboard drag-and-drop, moving items 43, 61 and 65 to complete; Checkpoint 6 built the workflow trigger/condition/action engine on the existing outbox, moving items 56, 57, 58 and 60 to complete; Checkpoint 7 built AI Account Summary, Account Intelligence, Next-Best-Action, AI email drafting, meeting-to-CRM extraction and rule-based prioritization on the AI gateway, moving items 1, 4, 5, 6, 7, 8 and 10 to complete and item 9 from missing to partial — only Custom modules (40) remains missing; see the Checkpoints table below for what each checkpoint changed).

- **The CRM core is solid.** Accounts, contacts, leads, deals, pipeline,
  activities, tasks, meetings, notes, attachments, email, search, saved views,
  import/export, custom fields, blueprints, RBAC, record-level visibility,
  row-level-security tenant isolation and audit logging are implemented end to
  end. Each has a backend module, a migration, a real frontend screen, and
  integration tests.
- **AI now covers every checkpointed feature except custom modules.**
  Checkpoint 7 built `products/crm/ai_insights/*` on the same AI gateway
  Market Insights uses: account/deal/lead summaries, Account Intelligence,
  Next-Best-Action, AI email drafting, meeting-to-CRM extraction (never
  writes until a user confirms), a natural-language question box (read-only,
  translated into the existing report engine — never raw SQL), and
  rule-based prioritization with an AI-narrated explanation ("rules first, AI
  explanation second" — the score itself is never a model's guess). Natural-
  language *commands* that write data remain out of scope (#9 stays partial;
  see its row below).
- **The "AI not connected" issue has two layers.** First, most AI screens show
  the message unconditionally, whatever the configuration. Second, the one
  screen that checks, Market Insights, depends on the environment variables
  for the selected provider. See [AI Connection Investigation](#ai-connection-investigation).
- **What stands out as missing in the Zoho comparison:** a layout/section form
  builder with conditional fields, drag-and-drop (Kanban, fields, dashboards),
  inline and bulk editing, a workflow-rules engine, a custom report builder,
  custom modules, and custom roles.
- **Nothing that is complete needs rebuilding.** Most gaps extend an existing
  module, e.g. layouts on top of custom fields, workflows on top of the outbox
  and event spine, and AI features on top of the gateway.

---

## Feature Audit

Legend: ✅ COMPLETE · 🟡 PARTIAL · 🔴 MISSING. Paths are relative to the repo
root. `BE` = `backend/app/products/crm/`, `PF` = `backend/app/platform/`,
`FE` = `frontend/`. Endpoints are under `/api/v1`.

### A. AI / Intelligence

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 1 | AI connection/integration | ✅ | Gateway `PF/ai/` (`service.py` `AiGatewayService`, `provider.py` `AnthropicResearchProvider` + `GeminiResearchProvider`); streaming, continuations, Redis rate limit, append-only prompt versions (`platform.ai_prompt_versions`, migration `20260827_0100`). **Checkpoint 7:** `BE/ai_insights/structured.py:run_structured` adds the generic non-research "completion" path (`web_search=False`) every structured-output feature uses; the gateway now backs two product modules, not one. | — | #2, #3 |
| 2 | AI provider configuration | 🟡 | Env-only, via `Settings` in `backend/app/core/config.py`: `AI_PROVIDER` (`anthropic`\|`gemini`, default `anthropic`), per-provider key, model, limits. | No admin UI: `FE/app/(crm)/ai-settings/providers/page.tsx` is a static `AiUnavailable` placeholder. No DB-stored credentials on this branch (no `credentials.py`/`registry.py`, no `ai_provider_credentials` migration). Optional: read-only provider/model display from `/ai/status`. | #3 |
| 3 | AI health/status | 🟡 | `GET /ai/status` → `{configured, model}` (`PF/ai/router.py`). Checks that a key is **present** for the selected provider. | No live check. A revoked or invalid key still reports `configured: true` until a real call fails with `ai_not_configured`. Only 1 of 12 AI screens (Market Insights) calls it. Add provider name + admin-only live probe. | — |
| 4 | AI Account Summary | ✅ | **Checkpoint 7:** `BE/ai_insights/service.py:account_summary` (also `opportunity_summary`/`lead_summary`) builds permission-filtered context (`context.py`) and a validated `RecordSummaryOutput`, stored append-only in `crm.ai_generations`. `GET/POST /crm/ai-insights/{accounts,opportunities,leads}/{id}/summary`. `FE/components/crm/ai/AiRecordPanel.tsx` renders it as an "AI" card on the Account/Deal/Lead 360 pages, with Generate/Refresh and thumbs up/down feedback. | — | #1, #12 |
| 5 | AI Account Intelligence | ✅ | Market Insights (web research) unchanged. **Checkpoint 7 adds the CRM-internal half:** `account_intelligence` — summary, relationship health + rationale, risks, opportunities, recommended actions, missing information, all grounded in the account's own CRM data (never generic advice) via `AccountIntelligenceOutput`. `GET/POST /crm/ai-insights/accounts/{id}/intelligence`, rendered on Account 360's AI card. The old fixtures (`FE/features/ai/insights/mock-data.ts`) were not imported. | — | #1, #4 |
| 6 | AI Next-Best-Action | ✅ | **Checkpoint 7:** `next_best_action_for_opportunity`/`_for_lead` recommend one concrete action with urgency and evidence (`NextBestActionOutput`), rendered per-record on the AI card. A ranked queue across every open deal/lead lives on `FE/app/(crm)/ai/next-best-action/page.tsx`, backed by the rule-based priority scores (#10) — ranking needs no AI call; "Explain" narrates one score. The pre-existing mock components (`FE/components/crm/ai/nba/*`) were left in place, unused, rather than wired to real data — see Known limitations. | — | #1, #10, #20–24 |
| 7 | AI email generation | ✅ | **Checkpoint 7:** `POST /crm/ai-insights/email-draft` (`EmailDraftRequest`: exactly one of contact/account/opportunity/lead id, a tone, a free-text instruction sent as delimited data) returns a subject/body (`EmailDraftOutput`) — never sends. `FE/components/crm/emails/ComposeEmailDrawer.tsx` gained a "Draft with AI" panel that fills the subject/body fields for review before Send. | — | #1, #27 |
| 8 | AI meeting/activity → CRM updates | ✅ | **Checkpoint 7:** `POST /crm/ai-insights/meetings/extract` reads pasted notes/a transcript as delimited user text and returns a structured extraction (summary, participants, key points, requirements, objections, commitments, sentiment, proposed follow-ups as TASK/NOTE/OPPORTUNITY_AMOUNT items) — nothing is written. `POST /crm/ai-insights/meetings/{id}/apply` creates only the items the user selects, through each entity's own service (`TaskService`/`NoteService`/`OpportunityService`), permission-checked per kind (a real gap the previous session's draft had — writing regardless of the caller's `tasks`/`notes`/`opportunities` permission — fixed before this checkpoint closed). `FE/components/crm/ai/AiRecordPanel.tsx`'s "Meeting notes → CRM" card on Account/Deal pages. The orphan `AIMeetingAssistant.tsx` was left in place, unused — see Known limitations. | — | #1, #20–23, #56 |
| 9 | Natural-language CRM commands | 🟡 | **Checkpoint 7:** `POST /crm/ai-insights/query` translates a plain-language question into a `CustomReportDefinition` (`NlQueryTranslation`, `understood: false` with a clarification when the question can't be confidently expressed) and runs it through the *existing* `CustomReportEngine` — the model never sees or returns raw rows, never writes SQL. Re-checks the translated report's own module permission even though `ai_insights` already gated the request, so the AI path cannot answer for a module the caller cannot otherwise view. `FE/app/(crm)/ai/insights/page.tsx`'s question box. | Read-only by design (§10 of this module's own docstring: "never executes a query itself" beyond the guarded report engine) — a *command* that writes data ("mark this lead qualified") is not built. The orphan `AICommandBar.tsx` was left in place, unused. | #1, #42, #43 |
| 10 | AI deal/lead prioritization | ✅ | **Checkpoint 7:** `BE/ai_insights/prioritization.py` — pure, unit-tested functions scoring an open deal/lead from real fields (deal value, close date, win probability, days since last activity, overdue tasks) into HIGH/MEDIUM/LOW with named, checkable reasons; no model call. `GET /crm/ai-insights/priority/{opportunities,leads}` for the ranked queue, `POST .../explain` for a one-paragraph AI narration of an *already-computed* score (never a new reason). `FE/app/(crm)/ai/next-best-action/page.tsx` renders both queues; not yet surfaced on the Accounts/Opportunities/Leads list or Kanban views themselves. | Score not yet shown on the record list/Kanban views, only the dedicated queue page. | #1, #15, #20 |

### B. CRM Core

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 11 | Accounts | ✅ | `BE/accounts/*`; CRUD + CSV export; soft delete, `merged_into_id`; `FE/app/(crm)/accounts/*`. | — | — |
| 12 | Account 360 | 🟡 | **Checkpoint 2:** tabbed (`Overview`/`Contacts`/`Deals`/`Activities`/`Emails`/`Notes`/`Files`/`Timeline`) via `FE/components/crm/shared/Tabs.tsx`. Summary header (`FE/components/crm/accounts/AccountSummary.tsx`) reads `GET /crm/accounts/{id}/overview` (`BE/accounts/overview.py`, `service.py:overview`): open pipeline value, won revenue, contacts count, open tasks count, next meeting, owner name, primary contact — all record-visibility-scoped, no N+1. Company details now include phone (`crm.accounts.phone`, migration `20260914_0100`). **Checkpoint 3:** the Timeline tab now merges Task created/completed, sent Email and Notes into the same stream as activities, deals and contacts (see #24). **Checkpoint 7:** gained an "AI" tab (`FE/components/crm/ai/AiRecordPanel.tsx`) — AI summary, Account Intelligence and a meeting-notes-to-CRM extractor, all on real CRM data (#4, #5, #8). | Still no dedicated open-tasks/upcoming *list* panel on the Account page — only the count. | #4, #16, #21, #24 |
| 13 | Contacts | ✅ | `BE/contacts/*`; CRUD, export, merge; `FE/app/(crm)/contacts/*`. | — | — |
| 14 | Contacts ↔ Accounts | ✅ | `crm.contacts.account_id`; `AccountContactsPanel` (`FE/components/crm/shared/RelatedLists.tsx`); create-from-account prefill. | — | — |
| 15 | Deals | ✅ | `BE/opportunities/*` (CRUD, export, stage change, reopen, history). | — | — |
| 16 | Deals ↔ Accounts | ✅ | `crm.opportunities.account_id` (NOT NULL); `AccountOpportunitiesPanel`, `ContactOpportunitiesPanel`. | — | — |
| 17 | Primary contacts | ✅ | **Checkpoint 2:** the Account 360 Contacts tab (`FE/components/crm/shared/RelatedLists.tsx:AccountContactsPanel`) is a real table with a star badge on the primary row and a "Make primary" action calling the existing `makeContactPrimary`/`POST /crm/contacts/{id}/primary`. Updates instantly (optimistic, then confirmed by the account summary's refetch) and is now audit-logged (`BE/contacts/service.py:set_primary` records an `accounts`-module `AuditLog` entry). | — | #12, #14 |
| 18 | Deal pipeline | ✅ | Per-tenant `crm.pipeline_stages` provisioned at signup; Kanban + table views; `FE/app/(crm)/pipeline-journey/*`. | — | — |
| 19 | Deal stages | 🟡 | Stage moves via `POST /crm/opportunities/{id}/stage` (state machine + blueprint), `/reopen`, `/history`; `GET /stages`. | Stages are **read-only** for tenants (`admin/crm-settings/page.tsx` says so). Need stage CRUD/reorder/probability admin. | #18, #55 |
| 20 | Activities | ✅ | `BE/activities/*`; types CALL/EMAIL/MEETING/NOTE/TASK; polymorphic `related_entity_*`. **Checkpoint 3:** added `duration_minutes` (migration `20260915_0100`), exposed on the quick "Log" form when logging a call. | — | — |
| 21 | Tasks | ✅ | `BE/tasks/*` (status machine, status counts, due-date index); `FE/app/(crm)/tasks/page.tsx`; due reminders. **Checkpoint 3:** added `due_before`/`due_after` list filters and a My Tasks / Upcoming / Overdue / Completed quick-view row on the Tasks page. | — | — |
| 22 | Calls | 🟡 | Logged as `Activity(type=CALL)`, now with `outcome` text **and a `duration_minutes` field** (Checkpoint 3). | Still no call direction or a result picklist, and no dedicated calls list distinct from the generic activity log. Telephony is out of scope. | #20 |
| 23 | Meetings | ✅ | `crm.meetings` (type, start/end, location, link, agenda, participants, reminder); `FE/app/(crm)/meetings/*`; calendar; reminders. | — | — |
| 24 | Timeline/activity history | 🟡 | `GET /crm/activities/timeline` + `ActivityTimelinePanel` on account/contact/lead/deal pages, unchanged. **Checkpoint 3 (new, separate from the above):** `BE/shared/timeline.py` is a shared read model — `GET /crm/accounts/{id}/timeline`, `/crm/contacts/{id}/timeline` (new) and `/crm/opportunities/{id}/timeline` (new) each merge activities, deal-created, stage-changed, task-created/completed, sent-email and note-added into one newest-first stream. Notes and email are read through each module's own visibility predicate (`NoteService.visibility_filter`, `emails.policies.readable_messages`), not a re-derived copy. `FE/components/crm/shared/RecordTimeline.tsx` renders it on Account, Contact and Opportunity detail pages. | Leads still show the activities-only `ActivityTimelinePanel`, not the merged stream — the same generalization applied to Contact/Opportunity would extend to Leads directly. Field-edit history is still not a timeline source (no audit-to-timeline projection exists). | #20, #25–27, #70 |
| 25 | Notes | ✅ | `BE/notes/*` (visibility enum); `NotesPanel`. **Checkpoint 3:** `NoteService.visibility_filter` is now also reused (imported, not copied) by the shared timeline read model, so a note's presence on the merged timeline obeys the identical PRIVATE/TEAM/ORGANIZATION rule the Notes tab already enforced. | — | — |
| 26 | Files/attachments | ✅ | `PF/documents/*` (pre-signed MinIO/R2 URLs, validation, record-access inversion); `AttachmentsPanel`. **Checkpoint 3:** `BE/shared/attachments.py`'s `ATTACHABLE` map now also accepts `ACTIVITY` (a call recording or a meeting's shared deck belongs on the interaction, not on the whole account) — enabled at the API layer and integration-tested; no frontend surface yet, since there is no activity detail page to host an `AttachmentsPanel` on. | Activity attachments have no dedicated UI (documented limitation, not a bug). | — |
| 27 | Emails/email history | 🟡 | Phase D: compose, drafts, templates with placeholders, threads, outbox delivery, per-record `EmailsPanel`, delivery log. **Checkpoint 3:** a sent (not draft) message now also appears as an `email_sent` entry on the Account/Contact/Opportunity unified timeline (#24), reusing `emails.policies.readable_messages`. | Outbound only: no inbound capture (IMAP/Gmail/Outlook sync, BCC-dropbox). This remains explicitly undocumented-as-supported, not silently pretended — the emails module's own docstrings already say so. Add inbound later; no rebuild. | #24 |

### C. CRM Configuration / Form Builder

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 28 | Custom fields | ✅ | `BE/custom_fields/*` (JSONB `custom_fields` column on 5 entities; validation in `TenantScopedService` via `shared/custom_field_hook.py`); `FE/app/(crm)/admin/custom-fields/page.tsx`; `CustomFieldInputs` on create/edit forms; `CustomFieldsPanel` on detail pages. | — | — |
| 29 | Field types | ✅ | 12 types: TEXT, TEXTAREA, NUMBER, DECIMAL, DATE, DATETIME, BOOLEAN, EMAIL, URL, PHONE, PICKLIST, MULTI_PICKLIST. | Optional additions later: currency, lookup, formula, auto-number. | — |
| 30 | Picklists | ✅ | `crm.picklists`, `crm.picklist_options` (value/label, position, active, default); `/crm/picklists`. | — | — |
| 31 | Form builder | ✅ | **Checkpoint 4:** `BE/layouts/*` (`crm.record_layouts`/`layout_sections`/`layout_fields`/`layout_field_rules`) + `FE/app/(crm)/admin/layouts/page.tsx`: a real admin builder — pick an entity type, add sections, place built-in or custom fields, configure each (label/help/placeholder overrides, required override, read-only, visible, width), draft/publish lifecycle, live preview. Verified end-to-end in a running browser, not only statically. | Built-in field *placement* is fully modelled, editable and previewable, but the four entities' own create/edit forms still render their built-in fields from hardcoded JSX, not from the layout — only the custom-field portion of each form (via `CustomFieldInputs`) actually renders from a published layout today. See #41. | #34, #41 |
| 32 | Drag-and-drop form editing | ✅ | **Checkpoint 4:** `@dnd-kit` (the library choice deferred through Checkpoints 2–3, made once here as planned) drives `FE/components/crm/layouts/LayoutCanvas.tsx` — dragging a field reorders it or moves it to another section, persisted immediately via `POST /layouts/{id}/fields/reorder`; a failed request reloads from the server (optimistic-then-reconcile, the same pattern the custom-fields admin screen's own reorder already used). | — | #31, #34, #41 |
| 33 | Drag-and-drop field ordering | ✅ | **Checkpoint 4:** real drag ordering inside the layout builder (see #32), backed by `LayoutField.position`. The *original* target of this item — `FE/app/(crm)/admin/custom-fields/page.tsx`'s own field list, backed by `CustomFieldDefinition.position` and used when no layout is published — is a separate ordering and was intentionally left on its existing up/down buttons (already keyboard-accessible; not touched, not regressed). | — | #32 |
| 34 | Sections | ✅ | **Checkpoint 4:** `crm.layout_sections` (name, position, 1–2 columns) + section cards in the builder (add, rename inline, remove, column-count selector). | — | #41 |
| 35 | Section ordering | ✅ | **Checkpoint 4:** up/down buttons per section (kept off drag deliberately — sections are reordered far less often than fields, and this keeps the interaction keyboard-accessible without a second `DndContext`), persisted via `PATCH /layouts/{id}/sections/{id}`. | — | #34 |
| 36 | Conditional field visibility | ✅ | **Checkpoint 4:** `crm.layout_field_rules` (AND/OR, ten operators: equals/not_equals/contains/not_contains/greater_than/less_than/is_empty/is_not_empty/in/not_in) + `BE/layouts/evaluate.py` (pure, unit-tested precedence resolver) + server-side enforcement inside `CustomFieldValueService.resolve` (never bypassable by a client) + a mirrored TypeScript evaluator (`FE/features/crm/layouts/evaluate.ts`) driving a live preview in both the builder and every real entity form via `CustomFieldInputs`. Verified end-to-end against a running backend: a rule requiring a field when a lead reaches Qualified renders its required asterisk live and blocks a save that clears it, with the exact backend message shown in the form. | A rule's *target* must be a custom field (see #41's built-in-field note) — a condition may read any field, built-in or custom. | #34, #41 |
| 37 | Required/optional fields | ✅ | `is_required` on custom fields (enforced server-side on create; inactive fields exempt). Built-in required fields enforced by Pydantic schemas. **Checkpoint 4:** a published layout's field-level `is_required_override` and its rules' `effect_required` now layer on top of the definition's own `is_required` for custom fields — see #36. | Per-layout required overrides for *built-in* fields remain out of scope — see #41. | — |
| 38 | Default values | ✅ | `custom_field_definitions.default_value` (coerced like input), picklist `is_default`. | — | — |
| 39 | Field validation | ✅ | `min_value`/`max_value`, `min_length`/`max_length`, RE2-safe `pattern`; `custom_fields/validation.py`; `tests/unit/test_custom_field_validation.py`. | — | — |
| 40 | Custom modules | 🔴 | `CrmEntityType` is a closed enum of 5 types. | New entity kind with dynamic storage, permissions, list/detail UI. Large: schedule late. | #28, #41, #68 |
| 41 | Record layouts | 🟡 | **Checkpoint 4:** `crm.record_layouts` (entity type, DRAFT/PUBLISHED, one published per org+entity via partial unique index) fully built and administered — see #31/#32/#34/#35/#36. A published layout is the live authority for every custom field's conditional visibility/required state on all four entities' real forms (#36), and the full arrangement (sections, built-in *and* custom field placement) is real, persisted and rendered in the builder's own preview. | **Deliberately not done:** no per-role/per-profile layout assignment (one published layout per entity type, org-wide) — a real Zoho-style builder often supports several profiles; scoped out given the size already in this checkpoint. A rule's effect (required/visible) may only target a *custom* field, not a built-in one — a built-in field's requiredness is fixed by that entity's Pydantic schema, and changing that dynamically would mean rewriting core validation for all four entities, a materially larger and riskier change than this checkpoint should make. The renderer replacing each entity's hardcoded built-in-field JSX (as opposed to the custom-field block, which *is* layout-driven everywhere) was not attempted — see #31. | #28 |

### D. Record Management

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 42 | Global search | ✅ | `GET /crm/search` (**Checkpoint 5:** now 5 entities — accounts, contacts, leads, opportunities, activities; migrations `20260826_0100` + `20260917_0300`), tsvector, permission filtered in-query; `FE/components/crm/topbar/CommandPalette.tsx`; `test_search_performance.py`, `test_search.py`, `test_search_index_agreement.py`. | Activity hits are found and shown but have no detail page to click through to (no `/activities/{id}` route exists) — `hitHref` returns `null` for one and the palette renders it as informational rather than broken. | — |
| 43 | Advanced filtering | ✅ | **Checkpoint 5:** `reports/conditions.py` — a closed 12-operator vocabulary (eq/ne/contains/starts_with/ends_with/gt/gte/lt/lte/between/in/is_empty/is_not_empty) over an AND/OR condition group, reusing `ReportPeriod` for relative dates (`{"relative": "THIS_QUARTER"}`). Applied two ways from one engine: additively on every list endpoint via `?advanced_filter=<json>` (`shared/advanced_filter_query.py`, wired into leads/contacts/accounts/opportunities `list_*`), and as a saved view's new `advanced_filter` column (additive, alongside the existing flat `filters`). `FE/components/crm/reports/FilterEditor.tsx` (shared with the report builder) + `FE/components/crm/toolbar/AdvancedFilterBar.tsx`, wired on all four list pages. | A view's advanced filter is stored and validated but the list-page UI does not yet round-trip it through "save view"/"choose view" — choosing a saved view applies its flat `filters` only; the advanced condition, if the view has one, has to be rebuilt by hand. Custom fields are filterable but not selectable as the *field* of a condition beyond `eq`/`ne`/`contains`/`in`/`is_empty`/`is_not_empty` (the same set `custom_fields/filters.py` already offered). | #45, #61 |
| 44 | Sorting | ✅ | `sort_by`/`sort_dir` on lists, custom-field sort for sortable types; `DataTable` sorting. | — | — |
| 45 | Saved views | ✅ | `BE/views/*` (private/shared, default, 404-not-403 for others' private views); `SavedViewPicker` on accounts/contacts/leads/opportunities. **Checkpoint 5:** gained an additive `advanced_filter` column (migration `20260917_0200`), validated against the same field registry a custom report uses — see #43. | See #43 for the one gap (view apply/save does not yet carry the advanced filter). | #43 |
| 46 | Column customization | 🟡 | **Checkpoint 4:** `FE/components/crm/toolbar/ColumnChooser.tsx` (checkbox popover) is wired into the Leads list (`app/(crm)/leads/page.tsx`) alongside `SavedViewPicker`, which now reads/writes `SavedView.columns` (already stored server-side since Phase F, never round-tripped by a table until now) — choosing a view restores its column set, saving one captures it. | Only wired on Leads; Accounts/Contacts/Opportunities' `DataTable`s still render a fixed column set with no chooser. | #45 |
| 47 | Inline editing | ✅ | **Checkpoint 4:** `FE/components/crm/tables/DataTable.tsx` gained click-to-edit cells (`EditableCell`) — correct control per type (text/select/date/number), Enter/blur commits, Escape cancels, a `pending` re-entrancy guard against double-submit, inline error via `role="alert"`. `onCellEdit` calls the entity's existing `PATCH` endpoint, which already re-validates and audits server-side; a failed save reverts the cell rather than leaving a false value on screen. Wired on Leads/Opportunities/Contacts/Accounts for their editable columns (email, priority, status, industry, job title, deal value, expected close date, as applicable per entity). | Only the columns each page explicitly marked `editable` support inline edit; there is no "edit any column" mode. | — |
| 48 | Bulk editing | ✅ | **Checkpoint 4:** `POST /crm/{entity}/bulk-update` for leads/opportunities/accounts/contacts (`shared/service.py: TenantScopedService.bulk_update()`, looping per-id through the entity's own single-record update — so RecordVisibility, permission checks, and every field validator run exactly as they would for one record) returning a `BulkOperationResult` (succeeded ids + per-id failure reasons, never a silent partial success). `FE/components/crm/toolbar/BulkActionsToolbar.tsx`'s "Bulk edit" opens a drawer to set one field to one value across the current selection; `reportOutcome()` shows success/partial/failure counts from the real result. | One field at a time per bulk-edit action (not a multi-field patch in one call). | #49 |
| 49 | Bulk actions | 🟡 | **Checkpoint 4:** `BulkActionsToolbar` (shared across all four list pages) now offers bulk delete (`POST /crm/{entity}/bulk-delete`, confirmed), bulk edit (#48), and, via `extraActions`, bulk lead-status change and bulk opportunity-stage change (each going through the entity's real state-machine transition per record — `bulk_change_status`/`bulk_change_stage` — so an illegal transition is reported as a per-record failure, not silently applied or silently skipped); Merge remains an `extraActions` item where it already existed. | "Add to campaign" and "export selected" (export today is all-matching-filter, not selection-scoped) are not built. | #48 |
| 50 | Import | ✅ | `BE/imports/*`: CSV preview + commit for leads, accounts, contacts; row errors; audit; `FE/components/crm/import/ImportWizard.tsx`. **Checkpoint 4:** custom fields are now valid import targets (see #51) — the remaining gap is Opportunities as an importable entity at all. | Opportunities are not an importable entity. | — |
| 51 | Import field mapping | ✅ | Mapping step (CSV header → field) in the wizard; `mapping` JSON validated in `imports/router.py`. **Checkpoint 4:** a column can now be mapped to any of the org's active custom fields (`custom:<api_name>` targets, resolved and validated by `imports/catalog.py: custom_field_targets()`/`is_custom_field_target()`, routed into a nested `custom_fields` dict by `imports/service.py: _map_row()`); a required custom field left unmapped fails only that row, not the whole file. Mappings can be saved and reused: `ImportMappingTemplate` (`imports/models.py`, new table) + `ImportMappingTemplateService`, `GET/POST /crm/imports/{slug}/mapping-templates`, `DELETE .../{id}`, surfaced in the wizard as a "Saved mappings" chip row and a "Save this mapping as…" control. The mapping dropdown's previously-always-broken `custom_fields` (raw JSONB column, could never pass a string-cell validator) entry was also removed from the mapping options, the auto-suggest map, and the downloadable blank-template header — a pre-existing bug, not introduced this checkpoint, but fixed while touching this code since it was becoming more confusing next to the new per-field targets. | Import mapping templates are per-entity-slug only, not shareable across entities. | #28 |
| 52 | Export | ✅ | `GET /crm/{accounts,contacts,leads,opportunities}/export` (CSV-injection safe, `shared/csv_export.py`); `ExportButton`. | — | — |
| 53 | Kanban | ✅ | `FE/components/crm/kanban/KanbanBoard.tsx` on leads (by status) and opportunities (by stage); moves via row actions through the state-machine endpoints. | — | — |
| 54 | Kanban drag-and-drop | ✅ | **Checkpoint 2:** the Opportunities board (`FE/components/crm/kanban/KanbanBoard.tsx`) supports native HTML5 drag-and-drop, calling the same `handleStageChange` the existing dropdown uses — same blueprint validation, same win/lost confirmation, same revert-on-422. No new dependency: `@dnd-kit` stays deferred to the checkpoint where fields and dashboards need sortable lists too, so it is chosen once. **Checkpoint 3:** the Leads board is now wired the same way — a drop calls the identical `handleStatusChange`/`POST /crm/leads/{id}/status` the existing per-card dropdown already used, so the same state-machine table that already rejects a direct move to `CONVERTED` (covered by `test_crm_workflows.py`/`test_blueprints.py`) rejects it identically by drag. Cards already in `CONVERTED` are not draggable. **Checkpoint 4:** `onCardDrop` can now return a Promise; `KanbanBoard` tracks a `pendingIds` set and disables/dims a card while its own drop is in flight, so a fast repeat drop on the same card cannot fire a second, overlapping transition request. | Native drag-and-drop has no keyboard equivalent; the per-card dropdown remains as the accessible path on both boards. | #53, #55 |

### E. Automation

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 55 | Blueprints | ✅ | `BE/blueprints/*` (rules per from→to state, required fields, required permission; narrows only); `FE/app/(crm)/admin/blueprints/page.tsx`; `test_blueprints.py`, `configuration.spec.ts`. Unchanged this checkpoint — reused as-is by workflow `CHANGE_STAGE`/`CHANGE_STATUS` actions, which go through the identical guarded transition. | — | — |
| 56 | Workflow engine | ✅ | **Checkpoint 6:** `BE/workflows/*` — a rule evaluator subscribed to the transactional outbox. Every `create()`/`update()` (`shared/service.py: TenantScopedService`) and every guarded transition (`LeadService.change_status`, `OpportunityService.change_stage`) now enqueues `crm.record.event_occurred` (identifiers + a before/after delta of touched fields, never full record data — the outbox's own rule); `workflows.service.handle_record_event` matches it against active rules, evaluates conditions, runs actions. A second entry point, `workflows.service.scan_scheduled_workflows`, is an ARQ cron job for date/due-date rules with no triggering event. | — | #57, #58 |
| 57 | Workflow rules | ✅ | **Checkpoint 6:** `crm.workflow_rules` — `entity_type` (5 `CrmEntityType` members + `TASK`), `trigger_type` (`RECORD_CREATED`/`RECORD_UPDATED`/`FIELD_CHANGED`/`STAGE_CHANGED`/`STATUS_CHANGED`/`OWNER_CHANGED`/`SCHEDULED`/`TASK_DUE`), `trigger_config` (JSONB, shape per trigger), `condition_logic` (AND/OR) + `conditions` (JSONB list, the same `{field_key, operator, value}` shape and operator vocabulary `layouts.evaluate` already defines — reused via `workflows.conditions.matches_conditions`, not reimplemented). Created inactive, like a blueprint; `WorkflowRuleService._validate` refuses an unsatisfiable rule at save time (unreal column, wrong entity for a trigger/action, unsupported operator). | — | #56 |
| 58 | Workflow actions | ✅ | **Checkpoint 6:** `UPDATE_FIELD`, `ASSIGN_OWNER`, `CREATE_TASK`, `CREATE_ACTIVITY`, `CREATE_NOTE`, `SEND_EMAIL` (reuses `emails.EmailService`/`EmailTemplateService`/`emails.variables.resolve_variables`, never a second mail path), `SEND_NOTIFICATION` (reuses `platform.notifications.NotificationService.notify`), `CHANGE_STAGE`/`CHANGE_STATUS` (call `OpportunityService.change_stage`/`LeadService.change_status` directly — the same blueprint-guarded transition a person's own click uses; browser-verified that a blueprint-refused move is refused identically when a workflow attempts it). No webhook action — not built, see Known limitations. | Outbound webhook action. | #56, #59 |
| 59 | Notifications | 🟡 | `PF/notifications/*`: in-app bell, unread count, mark read; kinds `MEETING_REMINDER`, `TASK_DUE`, `RECORD_ASSIGNED`, and — **Checkpoint 6** — `WORKFLOW_ALERT` from the `SEND_NOTIFICATION` action (no migration needed: `Notification.kind` is a plain `String`, not a database enum). Still no user preferences, still polling not push. | User notification preferences; push delivery. | #58 |
| 60 | Follow-up automation | ✅ | **Checkpoint 6:** a workflow's `CREATE_TASK` action is real follow-up automation ("WHEN status changes to Qualified THEN create a task"), and `SCHEDULED`/`TASK_DUE` triggers cover "close date approaching" (`Opportunity.expected_close_date`, entity-allow-listed date fields) and "task overdue" (`Task.due_date`) — both via the same periodic ARQ scan, deduplicated per rule/record/day so an hourly tick cannot re-fire the same day twice. "No activity in N days" specifically was not built — no existing "last activity at" column to scan; documented as a known limitation, not attempted partially. | "No activity in N days" idle-record detection. | #56–58 |

### F. Reporting

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 61 | Reports | ✅ | `BE/reports/*`: 9 built-in catalogue reports (pipeline-by-stage, deals-closing, won-lost, sales-cycle-by-owner, lead-funnel, lead-conversion-by-source, activity-by-owner, overdue-tasks, accounts-by-industry), saved reports, folders, sharing, periods; record visibility applied. **Checkpoint 5:** a real ad-hoc report builder — `reports/{fields,custom}.py`, a per-entity allow-listed field registry (5 entities: leads, contacts, accounts, opportunities, activities) driving field selection, an AND/OR filter group (#43), `group_by`/`group_by_interval` (day/week/month/quarter/year via `date_trunc`) with count/sum/avg/min/max aggregation, sort, and an optional chart hint — validated and run through the identical four-step security model (`reports/service.py`'s own docstring) the catalogue already used. Custom definitions are stored on the *same* `saved_reports` table (`custom_definition` JSONB, migration `20260917_0100`, a CHECK constraint enforcing exactly one of `base_report_key`/`custom_definition`), so folders, sharing, periods, and dashboard tiles all work for a custom report with no change to any of them. `FE/components/crm/reports/ReportBuilder.tsx`, wired into `app/(crm)/reports/page.tsx` ("New custom report" + "Edit shape" on a custom saved report). | Select/group/aggregate targets are built-in fields only — a tenant's custom field can be used in a *filter* condition (reusing `custom_fields/filters.py`) but not as a selected column, a group key, or an aggregation target; doing so would need the same guarded-cast machinery custom-field filtering already has, under a second allow-list this checkpoint does not yet keep. | #43 |
| 62 | Dashboards | ✅ | `GET /crm/dashboard/summary` home screen + user dashboards `/crm/dashboard/boards` (migration `20260905_0100`). **Checkpoint 5:** the summary gained `weighted_pipeline_value` (open pipeline at each deal's own `win_probability`, unset treated as zero, not a guess), `won_revenue` (trailing 30 days), `lead_conversion_rate`, `revenue_trend` (6 months, zero-filled), `pipeline_by_owner`, and `lead_source_performance` (reused verbatim from `ReportRepository.lead_conversion_by_source` rather than a second query). | — | — |
| 63 | Dashboard widgets | ✅ | `crm.dashboard_components` → saved report, display CHART/TABLE/METRIC, 12-column grid. A custom report (#61) is usable as a tile with no change to this table. | — | — |
| 64 | Dashboard builder | ✅ | `FE/app/(crm)/dashboards/[id]/page.tsx` view/arrange modes; `PUT /boards/{id}/layout`. **Checkpoint 5:** a dashboard-wide date filter (`?date_from=&date_to=` on `GET .../data`) narrows every tile whose report has a date dimension for that one render — never persisted — and each rendered tile reports `date_filter_applied` so the UI can show which tiles the filter actually touched versus which have no date dimension at all and render unaffected. | — | #65 |
| 65 | Dashboard drag-and-drop | ✅ | **Checkpoint 5:** `@dnd-kit` (the library decision this branch deferred through Checkpoints 2–4, made once in Checkpoint 4's layout builder and reused here) drives tile reordering via `DndContext`/`SortableContext`/`useSortable`, calling the *same* `reorderComponents` the existing up/down buttons already called — one source of truth for order, two ways to reach it. The buttons are kept, not replaced: `@dnd-kit`'s sortable strategy ships a keyboard sensor alongside the pointer one, so drag is not an accessibility regression, but the buttons remain the path that needs no explanation on a touchscreen. | — | — |
| 66 | CRM analytics | 🟡 | Dashboard summary KPIs, pipeline journey, report library. **Checkpoint 5:** gained a real trend over time (`revenue_trend`, #62) and the ad-hoc report builder (#61) can construct further trends (e.g. any metric grouped by month) without new backend code. | Forecasting and targets/quotas are still not implemented — nothing computes a projection or compares an actual to a goal. | #61 |

### G. Enterprise

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 67 | Roles | 🟡 | System role templates + assignment/revoke (`PF/authorization/*`, `/roles`); `admin/roles` page is read-only. | Custom role create/edit (no `POST /roles`). | #68 |
| 68 | Permissions | ✅ | Module×action catalogue, `require_permission`, record-level VIEW_ALL / VIEW_TEAM, product gate; `test_rbac.py`, `test_record_visibility.py`. | — | — |
| 69 | Tenant isolation | ✅ | Postgres RLS (`core/rls.py`), non-superuser app role, `test_tenant_isolation*.py`, `test_cross_tenant_matrix.py`, `test_crm_rls.py`. | — | — |
| 70 | Audit logging | ✅ | `PF/audit/*` (redaction, out-of-band failure writes); `admin/audit-logs` page; `test_audit_logging.py`. | — | — |
| 71 | Security | 🟡 | Argon2, JWT with refresh rotation + reuse detection, login throttle, Redis rate limits, CORS, RLS privilege guard, secret redaction. | MFA, SSO/SAML, IP allow-lists: `admin/security` lists them as "Not implemented". | — |
| 72 | Performance | 🟡 | Composite indexes, search vectors, calendar/merge indexes, pagination, JSONB+GIN custom fields, search perf test. | No load/perf test suite beyond search; no caching layer for reports. | — |
| 73 | Error handling | ✅ | `core/exceptions.py` typed `AppError` codes; 503 `*_not_configured` states; frontend `notify`/`describeApiError`; commit errors surface as 500 (Phase H). | — | — |
| 74 | Regression testing | ✅ | 1684 backend tests (unit + integration), Ruff, mypy, TypeScript, ESLint, CI `.github/workflows/ci.yml`. | Keep adding per checkpoint. | — |
| 75 | E2E testing | 🟡 | 32 Playwright tests: auth, password reset, CRM journey, configuration (custom fields, views, calendar, blueprints), email, visibility. | None for AI, import, merge, dashboards builder, reports detail, Account 360. | all |

### Code & test map (by area)

| Area | Frontend | Backend | Models / migrations | Tests |
|---|---|---|---|---|
| AI | `app/(crm)/ai/*`, `app/(crm)/ai-settings/*`, `components/crm/ai/{AiRecordPanel,AiConnectionNotice,AiFeaturePending}.tsx`, `features/ai/{ai-insights,status,useAiStatus}.ts` | `platform/ai/*`, `products/crm/{market_insights,ai_insights}/*` | `ai_prompt_versions`, research sessions/messages (`20260827_0100`, `20260903_0100`); `crm.ai_generations` + `ai_feature`/`ai_generation_status`/`ai_feedback_rating` enums (`20260919_0100`) | `test_market_insights.py`, `test_ai_provider.py`, `test_gemini_provider.py`, `test_market_insights_prompts.py`; **Checkpoint 7:** `test_ai_insights.py`, `test_ai_insights_prioritization.py`, `test_ai_insights_structured.py`, `test_ai_insights_prompts.py` |
| Core records | `app/(crm)/{accounts,contacts,leads,opportunities,tasks,meetings,calendar,emails}/*`, `components/crm/shared/*` | `products/crm/{accounts,contacts,leads,opportunities,activities,tasks,notes,emails,calendar}/*`, `platform/documents/*` | `8224845a67ac`, `20260818_0100`, `20260909_0100` | `test_crm_workflows.py`, `test_calendar.py`, `test_crm_email.py`, `test_attachments.py`, `test_read_after_write.py` |
| Configuration | `app/(crm)/admin/{custom-fields,blueprints,crm-settings}/*`, `components/crm/forms/CustomFieldInputs.tsx` | `products/crm/{custom_fields,blueprints}/*` | `20260910_0100`, `20260912_0100` | `test_custom_fields.py`, `test_custom_field_validation.py`, `test_blueprints.py` |
| Record mgmt | `components/crm/{tables,toolbar,kanban,import,dialogs/MergeDialog.tsx,topbar/CommandPalette.tsx}` | `products/crm/{search,views,imports,merge}/*`, `shared/csv_export.py` | `20260826_0100`, `20260911_0100`, `20260913_0100` | `test_search*.py`, `test_saved_views.py`, `test_csv_import.py`, `test_csv_export.py`, `test_merge.py` |
| Reporting | `app/(crm)/{reports,dashboard,dashboards}/*` | `products/crm/{reports,dashboard}/*` | `20260905_0100` | `test_reports.py`, `test_report_library.py`, `test_dashboard*.py` |
| Enterprise | `app/(crm)/admin/{users,roles,teams,audit-logs,security,invitations}/*`, `context/AuthContext.tsx`, `lib/api-client.ts` | `platform/{auth,authorization,organizations,teams,audit,products,notifications,events,email}/*`, `core/{rls,rate_limit,tenant}.py` | `20260819_0200`, `20260821_0100`, `20260824_0100`, `20260906_0100`, `20260907_0100` | `test_rbac.py`, `test_tenant_isolation*.py`, `test_audit_logging.py`, `test_login_throttle.py`, E2E `frontend/e2e/*.spec.ts` |

---

## AI Connection Investigation

### Current AI architecture

```
Frontend page ── api-client ──► GET /api/v1/ai/status            (any signed-in member)
                              └► POST /api/v1/crm/market-insights (CRM product gate + market_insights perm)
                                     │
                                     ▼
                     MarketInsightsService  (BE/market_insights/service.py)
                       ├─ context.py  → permission-filtered CRM context
                       └─ AiGatewayService (PF/ai/service.py)
                            ├─ settings.ai_configured? no → AiNotConfiguredError (503 ai_not_configured)
                            ├─ Redis rate limit (AI_RATE_LIMIT_PER_HOUR)
                            ├─ pinned prompt version (platform.ai_prompt_versions)
                            └─ provider chosen by AI_PROVIDER (built on first use)
                                 ├─ "anthropic" → AnthropicResearchProvider  (model AI_MODEL, web search tool)
                                 └─ "gemini"    → GeminiResearchProvider     (model GEMINI_MODEL, grounding off by default)
                                        │
                                        ▼
                     ResearchResult → stored session/messages → JSON → Market Insights page
```

### Provider

Two providers are implemented in `backend/app/platform/ai/provider.py`:
Anthropic (`anthropic` SDK, default) and Google Gemini (`google-genai`). Only
the provider named by `AI_PROVIDER` is called. A key for the other vendor is
**not** a fallback (`Settings.ai_credential`).

### Configuration — environment variable names only

Read from `backend/.env` (pydantic-settings, `env_file=".env"`, relative to the
process's working directory) or the process environment:

| Variable | Purpose |
|---|---|
| `AI_PROVIDER` | `anthropic` (default) or `gemini` |
| `ANTHROPIC_API_KEY` | Key used when `AI_PROVIDER=anthropic` |
| `GEMINI_API_KEY` (alias `GOOGLE_API_KEY`) | Key used when `AI_PROVIDER=gemini` |
| `AI_MODEL` | Anthropic model (default `claude-opus-5`) |
| `GEMINI_MODEL` | Gemini model (default `gemini-flash-lite-latest`) |
| `GEMINI_GROUNDING_ENABLED` | Google Search grounding (default `false`, needs billing) |
| `AI_MAX_OUTPUT_TOKENS`, `AI_WEB_SEARCH_MAX_USES`, `AI_REQUEST_TIMEOUT_SECONDS`, `AI_MAX_CONTINUATIONS`, `AI_RATE_LIMIT_PER_HOUR` | Limits |
| `NEXT_PUBLIC_API_BASE_URL` (frontend), `CORS_ALLOWED_ORIGINS` (backend) | Must be correct for any API call, including `/ai/status`, to succeed |

### API flow

1. The page calls `getAiStatus()` → `GET /ai/status`
   (`frontend/features/ai/market-insights/index.ts:119`).
2. `ai_status` (`backend/app/platform/ai/router.py:73`) returns
   `configured = settings.ai_configured`, which is true only when the selected
   provider's key is non-empty (`backend/app/core/config.py:359`).
3. If `configured` is false, the page shows `NotConfigured` "AI is not
   connected" (`frontend/app/(crm)/ai/market-insights/page.tsx:357`).
4. If it is true, research posts to `/crm/market-insights`. The gateway builds
   the provider (`service.py:331`). A rejected credential at call time becomes
   `AiNotConfiguredError` (`provider.py:333`, `:502`). The frontend maps
   `ai_not_configured` to "AI is not connected…" (`index.ts:165`).

### Likely root cause

There are two causes; which one a person sees depends on the screen.

1. **Primary (code): most AI screens can never show "connected".**
   `frontend/components/crm/ai/AiUnavailable.tsx` renders "AI is not connected"
   unconditionally. Its copy says "there is no AI gateway in this system",
   which has been stale since the gateway shipped (migration `20260827_0100`).
   It is used by **AI Insights, Next-Best-Action, and 8 AI Settings pages**
   (overview, providers, features, agents, automations, copilot, knowledge,
   security-analytics). None of them calls `/ai/status`. Configuring a key
   changes nothing on these screens, because no feature exists behind them.
   Only `/ai/market-insights` consults the real status. `/ai-settings/prompts`
   is a working prompt editor, but it doesn't check the status either.
2. **Secondary (configuration): Market Insights reports `configured: false`
   whenever the selected provider has no key.** The usual ways this happens:
   - `GEMINI_API_KEY` is set but `AI_PROVIDER` is not `gemini`. The default is
     `anthropic`, so the gateway looks for `ANTHROPIC_API_KEY` and finds none.
   - The API runs without a `backend/.env`. This worktree has none: no
     `backend/.env`, no `frontend/.env.local`, no root `.env`.
   - On Railway, a variable change without a manual redeploy. The running
     container keeps the old settings (`get_settings()` is cached for the
     process's lifetime).
   - The key is present but invalid or revoked. `/ai/status` still says
     `configured: true` because it checks presence only. The failure appears
     only on the first research call, as `ai_not_configured`.

### Files involved

- `frontend/components/crm/ai/AiUnavailable.tsx`: hardcoded message
- `frontend/app/(crm)/ai/insights/page.tsx`, `ai/next-best-action/page.tsx`, `ai-settings/*/page.tsx`: callers
- `frontend/features/ai/market-insights/index.ts`: `getAiStatus`, error mapping
- `frontend/app/(crm)/ai/market-insights/page.tsx`: the one status-aware page
- `backend/app/platform/ai/router.py`: `/ai/status`
- `backend/app/core/config.py`: `ai_provider`, `ai_credential`, `ai_configured`
- `backend/app/platform/ai/service.py`, `provider.py`: provider build and error mapping
- `backend/.env.example`: documented variables

### Exact recommended fix (Checkpoint 1; not applied yet)

1. **Configuration, no code:** for Gemini, set both `AI_PROVIDER=gemini` and
   `GEMINI_API_KEY`. For Anthropic, set `ANTHROPIC_API_KEY`. Put them in
   `backend/.env` locally, or in the service variables on Railway followed by
   an explicit redeploy. Restart the API. Verify that `GET /api/v1/ai/status`
   returns `{"configured": true, "model": "…"}`.
2. **Backend:** extend `AiStatusResponse` with `provider`. Add an admin-only
   `GET /ai/health` that makes one minimal model call and reports
   `ok | credential_rejected | unavailable`. `/ai/status` stays cheap and
   presence-only.
3. **Frontend:** add a shared `useAiStatus()` hook in `frontend/features/ai/`.
   Make `AiUnavailable` status-aware, separating "AI not configured" from
   "AI connected, but this feature isn't built yet", and remove the stale
   "no AI gateway exists" copy. Show the provider/model read-only on
   `ai-settings/providers`.
4. **Tests:** integration tests for `/ai/status` (provider field, each provider
   with and without a key) and `/ai/health` with a stub provider. Add an E2E
   check that the AI pages render the configured state from the API.

---

## Completed Functionality

Accounts (11), Contacts (13), Contacts↔Accounts (14), Deals (15),
Deals↔Accounts (16), Primary contacts (17), Deal pipeline (18), Activities
(20), Tasks (21), Meetings (23), Notes (25), Files/attachments (26), Custom
fields (28), Field types (29), Picklists (30), Form builder (31),
Drag-and-drop form editing (32), Drag-and-drop field ordering (33), Sections
(34), Section ordering (35), Conditional field visibility (36),
Required/optional (37), Default values (38), Field validation (39), Global
search (42), Advanced filtering (43), Sorting (44), Saved views (45), Inline
editing (47), Bulk editing (48), Import (50), Import field mapping (51),
Export (52), Kanban (53), Kanban drag-and-drop (54), Blueprints (55), Workflow
engine (56), Workflow rules (57), Workflow actions (58), Follow-up automation
(60), Reports (61), Dashboards (62), Dashboard widgets (63), Dashboard builder
(64), Dashboard drag-and-drop (65), Permissions (68), Tenant isolation (69),
Audit logging (70), Error handling (73), Regression testing (74), AI
connection/integration (1), AI Account Summary (4), AI Account Intelligence
(5), AI Next-Best-Action (6), AI email generation (7), AI meeting→CRM (8), AI
prioritization (10). **57 in total** (Checkpoint 4 moved 31–36, 47 and 48
here; Checkpoint 5 moved 43, 61 and 65 here; Checkpoint 6 moved 56, 57, 58 and
60 here; Checkpoint 7 moved 1, 4, 5, 6, 7, 8 and 10 here — see each
checkpoint's own section below for what changed and what each item's
remaining gaps are).

Also present, though not in the audit list: calendar, record merge, lead
conversion, lead sources, campaigns, teams/departments, invitations, password
reset, app catalogue/enablement, Market Insights.

## Partial Functionality

AI provider configuration (2), AI health/status (3), Account 360 (12), Deal
stages (19), Calls (22), Timeline (24), Emails (27), Record layouts (41),
Column customization (46), Bulk actions (49), Natural-language commands (9),
Notifications (59), CRM analytics (66), Roles (67), Security (71), Performance
(72), E2E testing (75). **17 in total** (Checkpoint 4 moved Form builder (31)
and DnD field ordering (33) out to Completed, and moved Record layouts (41) in
from Missing; Checkpoint 5 moved Advanced filtering (43) and Reports (61) out
to Completed; Checkpoint 7 moved AI connection (1) and AI Account Intelligence
(5) out to Completed, and moved Natural-language commands (9) in from Missing
— see each checkpoint's own section below).

## Missing Functionality

Custom modules (40). **1 in total** (Checkpoint 5 moved Dashboard
drag-and-drop (65) out to Completed; Checkpoint 6 moved Workflow engine (56),
Workflow rules (57), Workflow actions (58) and Follow-up automation (60) out
to Completed — an outbound webhook action and "no activity in N days"
detection remain unbuilt within #58/#60 respectively, documented in the
feature-audit table rather than counted as a separate missing item; Checkpoint
7 moved AI Account Summary (4), AI Next-Best-Action (6), AI email generation
(7), AI meeting→CRM (8) and AI prioritization (10) out to Completed).

---

## Recommended Implementation Order

1. **AI connectivity first:** it unblocks every AI feature and is small.
2. **Account 360 + relationships:** mostly frontend aggregation over existing
   endpoints; gives the AI features a place to render.
3. **Unified timeline + calls + inbound-email groundwork:** the history the AI
   later summarises.
4. **Layouts/sections/conditional fields, then DnD, Kanban DnD, inline/bulk
   editing, and custom-field import mapping.** Choose one DnD library (e.g.
   `@dnd-kit`) once and reuse it for Kanban, fields and dashboards.
5. **Advanced filters, report builder, dashboard DnD:** the report builder
   needs the filter model.
6. **Workflow engine** on the existing outbox; notifications and follow-ups as
   its actions. Blueprints stay as they are (narrow-only).
7. **AI features** on real data: summary → intelligence → NBA → email drafts →
   meeting→CRM → NL commands → prioritization.
8. **Hardening:** custom roles, MFA/SSO decision, load tests, E2E for every
   checkpoint, docs.

Custom modules (40) are deliberately left out of the checkpoint plan below.
They are the largest item, touching storage, permissions, search, reports and
UI, and should be scoped separately once layouts (41) exist.

## Checkpoints

| # | Scope | Audit items | Status |
|---|---|---|---|
| **Checkpoint 1** | AI connection + verification | 1, 2, 3 (+ AiUnavailable fix) | ✅ Done |
| **Checkpoint 2** | Account 360 + Contacts + Deals + relationships | 12, 17, 54, 11/13–16/18 regression | ✅ Done |
| **Checkpoint 3** | Activities + Timeline + Notes + Files + Email CRM | 22, 24, 27 (+ 20, 25, 26 regression), 54 | ✅ Done |
| **Checkpoint 4** | Form builder + drag/drop + custom fields + conditional fields + Kanban + bulk/inline editing + import mapping | 31–36, 41, 46–49, 51, 54 | ✅ Done |
| **Checkpoint 5** | Search + Reports + Dashboards + Dashboard builder | 43, 61, 65, 66 (+ 42, 62–64 regression) | ✅ Done |
| **Checkpoint 6** | Workflows + Blueprints + Notifications + Automation | 56–60 (55 regression) | ✅ Done |
| **Checkpoint 7** | AI Account Intelligence + AI summaries + AI next-best-action + AI email + meeting-to-CRM + natural-language CRM | 4–10 | ✅ Done |
| **Checkpoint 8** | Security + performance + complete regression/E2E testing + documentation | 67, 71, 72, 75 (+ full suite) | Planned |

Rules for every checkpoint: extend existing modules and do not rebuild them.
Keep the "unset means not connected, never faked output" AI rule. Pass the
backend suite, Ruff, mypy, typecheck, lint, build and E2E. Update this file.
Commit on `claude/crm-zoho-gaps`.

## Checkpoint 1 — Completed (2026-09-11)

Continued and finished by a second session after the first ran out of tokens
mid-checkpoint (immediately before frontend typecheck/lint). This section
records independent verification of that session's work, not just its claims.

### Files changed

Backend:
- `backend/app/application.py` — logs the resolved AI configuration once at
  boot (provider, model, `configured`, `issue`; never the key).
- `backend/app/core/config.py` — `AiConfigurationIssue` literal,
  `Settings.ai_configuration_issue` property (distinguishes "no key at all"
  from "a key exists, but for the other provider"), `ai_health_check_timeout_seconds`.
- `backend/app/platform/ai/provider.py` — `AiAuthenticationError` (distinct
  from `AiNotConfiguredError`: a refused key is a different fix than a
  missing one), `AiConnectionState` enum, `ConnectionCheck` /
  `ConnectionCheckProvider`, `classify_anthropic_error` /
  `classify_gemini_error`, `.check()` on both providers (one minimal real
  request, no retries, bounded by `asyncio.wait_for`), `build_provider()`
  (the one place `AI_PROVIDER` is read to pick a class).
- `backend/app/platform/ai/service.py` — `AiConnectionService` (cheap
  `.status()` read from a Redis-cached verdict; `.check()` runs a real probe
  and writes the verdict + an audit entry); `AiGatewayService.run_turn` now
  records a verdict from every real research call too, so a working feature
  call also proves the connection.
- `backend/app/platform/ai/router.py`, `schemas.py` — `AiStatusResponse`
  gained `provider`, `state`, `reason`, `checked_at`, `check_source`,
  `latency_ms`, `error_code`; new `POST /ai/health` (`ai.ADMIN`, reuses the
  existing `ai` permission module — no catalog change needed).
- `backend/tests/integration/test_market_insights.py` — updated the
  `/ai/status` shape assertion.
- `backend/tests/unit/test_ai_connection.py` (new) — 48 tests: configuration/
  issue detection, Anthropic/Gemini error classification, `.check()` against
  scripted clients (success, empty response, refused key, timeout), the
  service's verdict caching (Redis TTL, key/model rotation invalidates the
  old verdict, fails open if Redis is down), and that no secret ever reaches
  a log, a Redis value, or a returned object.

Frontend:
- `frontend/features/ai/status.ts` (new) — the one client for
  `GET /ai/status` / `POST /ai/health`, plus presentation helpers
  (`describeNotConfigured`, `describeErrorCode`, `formatCheckedAt`).
- `frontend/features/ai/useAiStatus.ts` (new) — module-level shared store
  (`useSyncExternalStore`) so every AI screen reads one cached answer instead
  of each issuing its own request.
- `frontend/components/crm/ai/AiConnectionNotice.tsx` (new) — the single
  place that turns a status into a message; separates "not configured" /
  "credential rejected" / "provider failing" / "ready", never conflating them.
- `frontend/components/crm/ai/AiFeaturePending.tsx` (new) — replaces
  `AiUnavailable.tsx` (deleted) for the 9 screens with no feature behind them
  yet; reports the real connection state instead of a hardcoded claim, and
  says "this feature is coming next" when AI is actually connected.
- `frontend/app/(crm)/ai-settings/{agents,automations,copilot,features,knowledge,page,security-analytics}/page.tsx`,
  `ai/insights/page.tsx`, `ai/next-best-action/page.tsx` — migrated to
  `AiFeaturePending`.
- `frontend/app/(crm)/ai-settings/providers/page.tsx` — rebuilt from a
  placeholder into a real screen: live provider/model/state, an admin-only
  "Test AI connection" button (`POST /ai/health`), and the exact environment
  variables to set.
- `frontend/app/(crm)/ai-settings/prompts/page.tsx`,
  `frontend/app/(crm)/ai/market-insights/page.tsx` — now use
  `AiConnectionNotice`/`useAiStatus` instead of their own ad hoc status fetch.
- `frontend/features/ai/market-insights/index.ts` — `AiStatus`/`getAiStatus`
  now re-exported from `features/ai/status.ts` (one definition, not two).

### Root cause (confirmed, not just re-asserted)

Two independent causes, both present on this branch before the fix:

1. **9 of 12 AI screens rendered a hardcoded "AI is not connected" regardless
   of configuration** (`AiUnavailable.tsx`, deleted). Setting a key changed
   nothing on them because no feature exists behind them — verified by
   reading the deleted component and its callers directly.
2. **The one screen that did check (Market Insights) reported `configured:
   false` whenever `GEMINI_API_KEY` was set without `AI_PROVIDER=gemini`**,
   because `AI_PROVIDER` defaults to `anthropic` and the gateway looked for
   `ANTHROPIC_API_KEY`. Confirmed by `test_a_gemini_key_under_the_default_provider_is_not_configured`
   and reproduced by hand: `Settings(gemini_api_key=…)` alone leaves
   `ai_configured` `False` with `ai_configuration_issue ==
   "credential_for_other_provider"`.

The fix separates "not configured" (no key at all) from "credential rejected"
(a key exists and the provider refused it) from "provider failing" (a real
call errored) from "AI is connected" (a real call answered) — four states
that were previously all collapsed into one boolean.

### Tests

- `backend/tests/unit` (no Postgres/Redis required): **842 passed**, incl. the
  48 new `test_ai_connection.py` cases.
- `backend/tests/integration/test_market_insights.py`: collects cleanly (44
  tests), **not executed** — see Environment limitations below.
- Frontend: no unit/component test runner configured in this repo
  (`package.json` has no `test` script); coverage is typecheck + build +
  Playwright E2E (`test:e2e`, also blocked — see below).

### Static analysis

- **Ruff** (`uv run ruff check app tests migrations`, matching CI): clean.
- **mypy** (`uv run mypy app`, matching CI's `mypy app` — not `mypy .`, which
  the previous session apparently did not run: `mypy .` surfaces ~126
  pre-existing errors in `tests/`, none introduced by this checkpoint, that
  CI does not check): clean, 299 source files.
- **Frontend `tsc --noEmit`**: clean.
- **Frontend `eslint .`**: clean.
- **Frontend `next build`**: succeeds; all 53 routes generate, including
  every `/ai*` and `/ai-settings/*` page.

### Real AI connection verification

**Not performed against a live provider — no credential is available in this
environment**, and per the standing rule, that is reported honestly rather
than assumed or faked:
- No `backend/.env` existed before this checkpoint; no `ANTHROPIC_API_KEY` or
  `GEMINI_API_KEY` is set anywhere in the environment.
- A local-only `backend/.env` was created from `.env.example` (git-ignored,
  confirmed via `.gitignore` lines 40/43; not staged; contains no real
  secrets — both AI keys are blank, exactly as in the example) solely so the
  application could import for the unit-test run above. It does not enable
  live AI and was not required for anything else in this checkpoint.
- The code path was instead verified with real logic against **scripted**
  provider clients (no network): `AnthropicResearchProvider.check()` and
  `GeminiResearchProvider.check()` send the exact minimal request
  (`HEALTH_CHECK_PROMPT`, `HEALTH_CHECK_MAX_TOKENS`, no tools, no retries,
  `asyncio.wait_for`-bounded) and are asserted to classify a real success, an
  empty response, a refused key, and a timeout correctly; `AiConnectionService`
  is exercised end to end (`.check()` → Redis verdict → `.status()` reads it
  back) with a `StubCheck` standing in for the network call. This proves the
  backend → provider-selection → request-shape → response-classification
  chain; it does not prove any specific vendor's API answers today.

**To perform the live check**, whoever has a real key should:
1. Put exactly one of these in `backend/.env` (git-ignored):
   `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=…`, or
   `AI_PROVIDER=gemini` + `GEMINI_API_KEY=…` (or `GOOGLE_API_KEY`).
2. Bring up Postgres + Redis (`docker compose up -d`, blocked in this session
   — see below) and start the API.
3. `GET /api/v1/ai/status` → expect `{"configured": true, "state":
   "CONFIGURED", ...}`.
4. As an org admin, `POST /api/v1/ai/health` → expect `{"state":
   "AVAILABLE", "responded_model": "…", ...}`. This is the actual real round
   trip; `/ai/status` alone never calls a model.
5. Optionally run a Market Insights research call and confirm `/ai/status`
   now reports `state: "AVAILABLE"`, `check_source: "feature_call"`.

### Environment limitations

- **Docker was unavailable in this session**: `com.docker.service` is
  `STOPPED`, which (per prior experience in this environment) requires admin
  rights this session does not have; `Docker Desktop.exe` was not running
  either. This blocked:
  - `docker compose up -d` (Postgres/Redis/MinIO), and therefore the full
    1684-test backend suite and `backend/tests/integration/test_market_insights.py`
    specifically (44 tests, syntax-checked via `--collect-only` but not run).
  - Any live server to hit `/ai/status` or `/ai/health` over HTTP.
  - Playwright E2E (`npm run test:e2e`).
- Nothing above was faked or assumed to pass. Everything that does not need
  Docker was run to completion (see Tests/Static analysis).
- This worktree also had no `frontend/.env.local`; the frontend build does
  not require one (`NEXT_PUBLIC_API_BASE_URL` only matters for the running
  dev server hitting a real backend).

### Accidental-change / secret check

- `git diff --stat` scoped to exactly the files listed above; no unrelated
  file touched.
- Diff scanned for credential-shaped strings (`sk-ant-…`, `AIza…`,
  `api_key = "…"`); none found.
- `backend/.env` created for local testing is git-ignored and was not staged.
- No leftover references to the deleted `AiUnavailable` anywhere in
  `frontend/`.

## Checkpoint 2 — Completed (2026-09-14)

Account 360, the account-overview aggregate, the primary-contact UI, and
Kanban drag-and-drop. Audited the existing accounts/contacts/opportunities
modules first (§"Audit the existing implementation" in the checkpoint brief);
most of the *data model* was already there — the account/contact/deal
relationships, primary-contact promotion, stage history, blueprint-guarded
stage moves — and this checkpoint is mostly a frontend consolidation plus one
new backend read model, not new CRUD.

### What was already there (extended, not rebuilt)

- `crm.contacts.account_id`, `crm.opportunities.account_id`,
  `crm.opportunities.primary_contact_id` — real foreign keys, already used by
  `AccountContactsPanel`/`AccountOpportunitiesPanel`/`ContactOpportunitiesPanel`.
- `POST /crm/contacts/{id}/primary` (`ContactService.set_primary`) — the
  "exactly one primary contact" invariant was already correct (a single
  transactional UPDATE on the account row); the frontend client
  (`makeContactPrimary`) existed too. The only real gap was that nothing in
  the UI called it.
- `POST /crm/opportunities/{id}/stage` — blueprint validation, win/loss
  handling, and `opportunity_stage_history` were already complete and already
  used by a stage dropdown, both on the deal detail page and on the existing
  (non-draggable) Kanban board.
- Contact role/title/status/phone — `job_title`, `department`, `status`,
  `phone`, `mobile` already existed on `Contact`; nothing to add there.

### What was built

**Backend:**
- `backend/app/products/crm/accounts/models.py`, `schemas.py` — added
  `phone` (the one Account 360 field the model was missing); migration
  `backend/migrations/versions/20260914_0100_account_phone.py`.
- `backend/app/products/crm/accounts/overview.py` (new) — a "dedicated read
  model" (ARCHITECTURE-BOUNDARIES.md rule 6, the same pattern
  `dashboard/repository.py` established): `AccountOverviewRepository`
  (contacts count, open/won deal count+value+currency, open tasks count,
  owner name via the Platform's `organizations_for_session().member_directory`
  — never a direct `platform.users` read — primary contact, next meeting),
  and `merge_timeline_entries`, a pure function merging four independent
  timeline sources newest-first.
- `backend/app/products/crm/accounts/service.py` — `AccountService.overview()`
  and `.timeline()`, each resolving `RecordVisibility` per sub-module
  (contacts/opportunities/tasks) exactly as the list endpoints do, so the
  summary can never show more than the caller's own lists would.
- `backend/app/products/crm/accounts/router.py` — `GET
  /crm/accounts/{id}/overview` and `GET /crm/accounts/{id}/timeline`.
- `backend/app/products/crm/contacts/service.py` — `set_primary` now writes
  an `accounts`-module `AuditLog` entry (before/after `primary_contact_id`),
  closing the "record history" ask; `record_change` no-ops when nothing
  changed, so re-promoting the incumbent writes nothing.
- Notes are deliberately **excluded** from the unified timeline: their
  visibility (private/team/organization) is the notes module's own policy,
  and re-deriving it in a new read model would be a second, easier-to-get-
  wrong copy of a security check that already exists correctly. Verified with
  a dedicated test (`test_timeline_excludes_notes`).

**Frontend:**
- `frontend/app/(crm)/accounts/[id]/page.tsx` — rebuilt around the existing
  `Tabs` component (already used by `admin/custom-fields` and
  `NbaDetailsDrawer`, not new): `Overview` / `Contacts` / `Deals` /
  `Activities` / `Emails` / `Notes` / `Files` / `Timeline`. `Overview` keeps
  company details (now with Phone), address, description and custom fields;
  every other tab is one existing panel, unchanged, just no longer
  stacked on one page.
- `frontend/components/crm/accounts/AccountSummary.tsx` (new) — the KPI strip
  (`KpiCard`, already used elsewhere) reading `GET .../overview`: open
  pipeline, won revenue, contacts, open tasks, owner, primary contact, next
  meeting.
- `frontend/components/crm/accounts/AccountTimeline.tsx` (new) — renders the
  merged timeline with a per-kind icon and a link to the record each entry is
  about.
- `frontend/components/crm/shared/RelatedLists.tsx` —
  `AccountContactsPanel` rebuilt as a real table (Name/Role/Email/Status) with
  a star badge on the primary contact and a "Make primary" action per row
  (optimistic update, no page reload); `AccountOpportunitiesPanel` rebuilt as
  a table (Deal/Amount/Stage) with a "New deal" action. `ContactOpportunitiesPanel`
  (used by the Contact detail page) is unchanged.
- `frontend/components/crm/kanban/KanbanBoard.tsx` — added optional native
  HTML5 drag-and-drop (`onCardDrop`, `getItemId`, `canDrag`), wired into the
  Opportunities page's board so a drop calls the *same* `handleStageChange`
  the existing dropdown calls — same blueprint validation, same win/loss
  confirmation dialog, same revert-on-422. No new dependency: `@dnd-kit` stays
  deferred to the checkpoint where custom fields and dashboards also need
  sortable lists, so it gets chosen once for all three. Native drag-and-drop
  has no keyboard equivalent, so the existing dropdown remains as the
  accessible fallback on both boards; the Leads board was not wired for drop
  (out of scope — this checkpoint's brief named Deals throughout).
- `frontend/app/(crm)/accounts/page.tsx`, `frontend/features/crm/accounts/index.ts`
  — Phone added to the list/edit form and the API client; `AccountOverview`/
  `AccountTimelineEntry` types and `getAccountOverview`/`getAccountTimeline`
  added.

### Tests

- `backend/tests/unit/test_account_timeline.py` (new, **runs without
  Postgres**): 5 tests for `merge_timeline_entries` — newest-first merge
  across sources, the limit cutoff, an empty source, no sources, and a tie at
  the same timestamp. All pass.
- `backend/tests/integration/test_account_relationships.py` (new, 13 tests,
  **requires Postgres — not executed, see Environment limitations**):
  overview aggregates match real created data; won revenue counts only
  closed-won deals; owner/primary-contact name resolution; an empty account
  reports zeros, not errors; promoting a contact demotes the incumbent; a
  contact with no account cannot be made primary; the timeline merges all
  three non-activity sources and respects `limit`; notes are excluded; **a
  rep's overview/timeline count only what the rep can see, not what an admin
  added to the same account** (the record-visibility property Checkpoint 2
  §13 requires, checked the same way
  `test_the_dashboard_counts_only_what_the_rep_can_open` checks it for the
  org-wide dashboard); another organization's account is 404 on both new
  routes; a random id is 404, not 500.
- Verified via `pytest --collect-only`: 13 items, no syntax errors.
- Existing tests: not weakened or deleted. Full backend unit suite re-run
  after every change (see Static analysis below).

### Static analysis

- **Ruff** (`app tests migrations`): clean.
- **mypy** (`app`, matching CI): clean, 300 source files.
- **Frontend `tsc --noEmit`**: clean.
- **Frontend `eslint .`**: caught one real issue during development —
  `RelatedLists.tsx` was syncing local state from a prop inside a
  `useEffect` (`react-hooks/set-state-in-effect`); fixed by computing the
  optimistic override without an effect at all. Clean after the fix.
- **Frontend `next build`**: succeeds; all 53 routes generate.
- **Backend `pytest tests/unit`**: **849 passed** (848 pre-existing + the new
  timeline-merge file), 0 failed.

### A bug caught before it ran

`AccountOverview`/`TimelineEntry` are `@dataclass(frozen=True, slots=True)`.
The router's first draft built the response with `**overview.__dict__` —
which raises `AttributeError` at runtime on any slotted dataclass, since
`slots=True` removes the per-instance `__dict__` entirely. mypy does not
catch this (attribute access on `__dict__` typechecks fine); it would have
surfaced only when `GET /accounts/{id}/overview` was actually called. Fixed
with `dataclasses.asdict(...)` before it was ever exercised — see
`backend/app/products/crm/accounts/router.py`.

### Environment limitations

- **Docker was unavailable in this session** (same constraint as Checkpoint
  1: `com.docker.service` is `STOPPED`). This blocked
  `backend/tests/integration/test_account_relationships.py` (13 tests,
  syntax-checked via `--collect-only`, not executed) and any live-server
  check of the two new routes over HTTP.
- **The Browser preview tooling could not reach this worktree.** `preview_start`
  resolved `.claude/launch.json` and ran `next dev` against a *different*
  worktree (`zoho-s3k-gap-analysis-686c6b`) than the one this session's file
  edits and git history live in (`s3k-crm-local-setup-0f83a7`) — the dev
  server it launched failed immediately with "couldn't find next/package.json"
  because it resolved the *other* worktree's `frontend/app`. This is a
  session-level plumbing mismatch (this session entered
  `s3k-crm-local-setup-0f83a7` via `EnterWorktree` mid-task; the Browser
  preview subsystem still points at the worktree the session was launched
  in), not a bug in the code being reviewed here. It means no live click-
  through of the new tabs, the "Make primary" button, or Kanban drag-and-drop
  was possible in this session. Verification for the UI work is therefore
  static only: `tsc`, `eslint`, `next build`, and manual code review — no
  screenshot, no browser console check. **Recommended before trusting this
  checkpoint's frontend in production:** open `/accounts/{id}` in a real
  browser against a running backend and click through all eight tabs, the
  "Make primary" action, and a drag on the Opportunities board.
- Nothing above was faked or assumed to pass.

### Accidental-change / secret check

- `git diff --stat` scoped to exactly 11 modified + 5 new files, all named
  above; nothing unrelated touched.
- Diff scanned for credential-shaped strings; none found.
- `git diff --check`: no whitespace errors (only pre-existing LF→CRLF
  conversion notices, not errors).

## Checkpoint 3 — Completed (2026-09-15)

Audited every module named in the brief before writing anything
(activities/tasks/notes/emails/documents backend, and the panels/pages that
already read them) and found the backend for most of it already complete and
solid: Tasks is a full module with its own status machine; Notes already
enforces PRIVATE/TEAM/ORGANIZATION visibility in SQL; Emails (Phase D) already
has compose/draft/send/threads/templates over the transactional outbox;
Meetings is already an `Activity(type=MEETING)` with a scheduling extension,
already shown on the existing Calendar — there is no second calendar system to
build or avoid. This checkpoint is therefore concentrated on the two things
the audit found genuinely missing: a **unified timeline** that actually merges
every source (Checkpoint 2 built this for Account only, and excluded Notes and
Email), and a handful of small, well-scoped additions the audit could point to
by name (call duration, task quick-views, a follow-up flow, Leads Kanban
drag-and-drop, Activity-level attachments).

### What was already there (extended, not rebuilt)

- `BE/tasks/*` — full CRUD, status machine (`PENDING`→`IN_PROGRESS`→
  `COMPLETED`/`CANCELLED`), status-counts endpoint, `related_entity_*` linking,
  `RecordVisibility`. Nothing needed rebuilding; only `due_before`/`due_after`
  filters were missing for the quick-view row.
- `BE/notes/*` — `NoteService.visibility_filter` already existed as the single
  point of truth for who may read a note. Reused verbatim (imported, not
  copied) by the new timeline read model.
- `BE/emails/*` (Phase D) — compose, draft, send, threads, templates, the
  outbox pattern, `readable_messages` (draft-privacy) and
  `may_see_blind_copies` policies. Reused `readable_messages` verbatim for the
  same reason.
- `crm.meetings` + `FE/app/(crm)/calendar/*` — a meeting is already an
  activity with a scheduling extension, already on the one Calendar. Untouched.
- `PF/documents/*` — the attachments module's `ATTACHABLE` inversion pattern
  (`BE/shared/attachments.py`) already existed for Account/Contact/Lead/
  Opportunity/Campaign/EmailMessage; adding `ACTIVITY` was one dictionary entry
  plus a test, not new plumbing.
- `FE/components/crm/kanban/KanbanBoard.tsx` — the native HTML5 drag-and-drop
  Checkpoint 2 built for Opportunities was already generic; wiring Leads to it
  needed only three new props on the existing `<KanbanBoard>` usage.

### What was built

**Backend:**
- `backend/app/products/crm/shared/timeline.py` (new) — the reusable half of
  Checkpoint 2's `accounts/overview.py` timeline, lifted out so Contact and
  Opportunity can build the same kind of unified timeline without a second
  copy of each query (ARCHITECTURE-BOUNDARIES.md rule 6, the same "dedicated
  read model" pattern). Holds `TimelineEntry`, `merge_timeline_entries`, and
  one source function per event kind: `activity_entries` (delegates to
  `ActivityService.timeline`), `deal_created_entries`/`stage_changed_entries`
  (parameterized by an `opportunity_filter` predicate, so the same query
  serves "this account's deals", "this contact's deals" and "this deal
  itself"), `task_entries` (up to two entries per task — created, and
  completed when it is), `email_entries` (SENT messages only, filtered by the
  emails module's own `readable_messages`), and `note_entries` (filtered by
  the notes module's own `NoteService.visibility_filter`). No source function
  re-derives an authorization rule another module already owns.
- `backend/app/products/crm/accounts/overview.py` — refactored to import the
  shared entry shape/merge/sources instead of defining its own; kept only
  what is genuinely account-specific (the KPI summary, and the two sources it
  scopes by `account_id`). `AccountService.timeline()` now also merges task,
  email and note entries.
- `backend/app/products/crm/contacts/service.py` + `router.py` — new
  `ContactService.timeline()` and `GET /crm/contacts/{id}/timeline`. Deal
  entries are scoped by `primary_contact_id`, not by the contact's account —
  a contact's timeline shows deals it is the primary contact for, not every
  deal on the account (the account's own timeline is where that broader view
  belongs).
- `backend/app/products/crm/opportunities/service.py` + `router.py` — new
  `OpportunityService.timeline()` and `GET /crm/opportunities/{id}/timeline`.
  Its own creation and its own stage history join the same merged stream as
  activities/tasks/email/notes, by calling the shared `deal_created_entries`/
  `stage_changed_entries` with a filter matching only that one opportunity —
  not a hand-written duplicate.
- `backend/app/products/crm/shared/schemas.py` — added `TimelineEntryResponse`
  (the wire shape every one of the three `/timeline` endpoints returns), next
  to the module's existing `CustomFieldValues` for the same reason: five
  entity schema modules need one identical shape.
- `backend/app/products/crm/activities/{models,schemas}.py` +
  `migrations/versions/20260915_0100_activity_call_duration.py` — added
  `duration_minutes` (nullable, `>= 0` check constraint) to `Activity`. A
  plain column, not a second one-to-one extension table like `meetings`: a
  call needs exactly one number, not five scheduling columns.
- `backend/app/products/crm/shared/attachments.py` — `ATTACHABLE` gained
  `ACTIVITY_ENTITY_TYPE`, so a file (a call recording, a meeting's shared
  deck) can be attached to the interaction itself, not only to the account it
  happened against. Tasks and notes remain deliberately absent, per the
  existing docstring's reasoning.
- `backend/app/products/crm/tasks/{service,router}.py` — added `due_before`/
  `due_after` filters (a task with no due date matches neither — it is not
  "overdue" any more than an unscheduled meeting could be), powering the
  Tasks page's Overdue/Upcoming quick views.

**Frontend:**
- `frontend/components/crm/shared/RecordTimeline.tsx` (new) — the merged,
  newest-first timeline UI, parameterized by whichever `/timeline` endpoint
  the caller passes in, so Account, Contact and Opportunity share one
  rendering (icons, empty/loading/error states, click-through) instead of
  three copies. `frontend/components/crm/accounts/AccountTimeline.tsx` is now
  a five-line wrapper around it; Contact and Opportunity detail pages gained
  a new "Timeline" section using it directly.
- `frontend/features/shared/types/api.ts` — added the shared `TimelineEntry`/
  `TimelineEntryKind` types (mirrors the backend's `TimelineEntryResponse`);
  `frontend/features/crm/{contacts,opportunities}/index.ts` added
  `getContactTimeline`/`getOpportunityTimeline`.
- `frontend/components/crm/shared/RecordPanels.tsx` — `ActivityTimelinePanel`
  gained a duration-in-minutes field on the quick "Log" form (shown only for
  `type === 'CALL'`, shown on each logged call's row), and a "Create
  follow-up" action on any completed call or meeting: an inline one-field
  task form, pre-titled from the activity, that writes through the same
  `POST /crm/tasks` every other task creation uses with the polymorphic link
  already filled in — "Complete Call → Create Follow-up → Task → visible on
  the record's timeline" end to end, reusing existing task infrastructure
  rather than a new automation engine (Checkpoint 6 owns that).
- `frontend/app/(crm)/tasks/page.tsx` — a My Tasks / Upcoming / Overdue /
  Completed / All Tasks quick-view row above the existing search/status/
  priority filters, reading the new `due_before`/`due_after` params plus
  `assigned_to_id: currentUser.id`.
- `frontend/app/(crm)/leads/page.tsx` — the Leads Kanban board now takes
  `getItemId`/`canDrag`/`onCardDrop`, wired to the *same* `handleStatusChange`
  the existing per-card dropdown already called. `CONVERTED` cards are not
  draggable (conversion needs the dedicated `/convert` endpoint, which creates
  an account and a contact together); the backend's own state-machine table
  already rejects any other direct move to `CONVERTED`, however it is
  attempted, so dragging a card onto that column is rejected exactly as
  selecting it from the dropdown already was.
- `frontend/features/crm/{activities,tasks,attachments}/index.ts` — added
  `duration_minutes` to `Activity`/`ActivityInput`; added `due_before`/
  `due_after` to `TaskListParams`; added `'ACTIVITY'` to
  `AttachableEntityType`.

### Tests

- `backend/tests/integration/test_record_timelines.py` (new, 20 tests, **run
  against real PostgreSQL — see below**): Contact timeline scopes deals by
  `primary_contact_id` not account; task created/completed entries; private
  notes excluded for a non-author, included for the author, content never
  echoed; a TEAM note is shared; Opportunity timeline includes its own
  creation and stage moves and excludes a sibling deal's; a random id is 404
  on both new routes; a sent email joins the timeline and a draft does not;
  Account timeline gained the same task/note assertions; call
  `duration_minutes` round-trips and rejects a negative value; task
  `due_before`/`due_after` correctly exclude/include by due date, with no
  due date matching neither; an activity can have a file reserved against it,
  and another tenant's activity returns 404 for the same request.
- `backend/tests/integration/test_account_relationships.py` — the Checkpoint 2
  note-exclusion test (`test_timeline_excludes_notes`) is now
  `test_timeline_includes_notes_without_echoing_their_content`, reflecting the
  Checkpoint 3 requirement that notes join the timeline; every other
  Checkpoint 2 test in the file is unchanged.
- `backend/tests/unit` — no new unit test file: `merge_timeline_entries` moved
  to `shared/timeline.py` but kept its existing tests passing by re-exporting
  the same names from `accounts/overview.py`
  (`tests/unit/test_account_timeline.py`'s 5 tests still import from there and
  still pass, unmodified).

### Static analysis

- **Ruff** (`app tests migrations`): clean.
- **mypy** (`app`, matching CI): clean, 301 source files.
- **Frontend `tsc --noEmit`**: clean.
- **Frontend `eslint .`**: caught one real issue during development — the new
  `RecordTimeline.tsx` reset its `items`/`error` state synchronously inside
  the fetch effect so switching records wouldn't show stale data
  (`react-hooks/set-state-in-effect`); fixed by removing the reset, matching
  the behaviour the original `AccountTimeline.tsx` already had (each of the
  three usages mounts once per record). Clean after the fix.
- **Frontend `next build`**: succeeds; all 53 routes generate.
- **Backend `pytest tests/unit`**: **851 passed**, 0 failed.
- **Backend `pytest tests/integration`**: run this checkpoint — Docker Desktop
  came up during the session for the first time in this branch's checkpoints
  (see below) — against a clean, freshly migrated, throwaway PostgreSQL plus
  real MinIO and Redis: **all 919 integration tests pass**, 0 failed. This
  includes every pre-existing suite (tenant isolation, RBAC, blueprints,
  dashboards, custom fields, saved views, merge, email delivery, attachments,
  audit logging, and all of Checkpoint 2's own tests), not only the ones this
  checkpoint added or touched — genuine end-to-end confirmation, not a subset.

### Docker became available mid-session, and what that changed

Unlike Checkpoints 1–2, Docker Desktop started successfully this session
(`Start-Process "Docker Desktop.exe"`, then a short poll for the containers'
health checks), bringing up `s3k-postgres` (port 5434), `s3k-minio` and
`s3k-redis`. Three real environment problems surfaced as a result, none of
them hypothetical — each was caught by an actual failing test run, not
inferred:

1. **`backend/.env`'s `DATABASE_URL` still pointed at port 5432** — a leftover
   from the placeholder `.env` a Docker-less Checkpoint 1 session created by
   copying `.env.example` verbatim. Port 5432 on this machine belongs to an
   unrelated project's Postgres container (`vms_postgres`), not this one.
   Fixed by pointing it at 5434, matching the root `.env`'s
   `POSTGRES_PORT=5434`.
2. **The `s3k_app` database's `alembic_version` row named a revision
   (`20260904_0100`) that does not exist in this branch's migration chain** —
   the persistent `postgres_data` volume predates a history rewrite on this
   branch. Rather than force-stamping or otherwise mutating a database that
   other local work may depend on, this checkpoint created a throwaway
   database (`checkpoint3_test`, owned by the existing `s3k_app` role) and
   ran `alembic upgrade head` against it from a bare `postgres` — every
   migration in the chain, including this checkpoint's new one, applied
   cleanly in order. All integration tests below ran against that database,
   not the shared `s3k_app` one, which was left untouched.
3. **`backend/.env`'s `STORAGE_ACCESS_KEY_ID`/`STORAGE_SECRET_ACCESS_KEY`
   (`s3k-local` / `change-me-locally`, again the `.env.example` placeholders)
   did not match the running `s3k-minio` container's actual credentials** —
   its persistent data volume predates the root `.env` these placeholders
   came from, so MinIO is still running with the random credentials it was
   first created with (`docker inspect s3k-minio` shows a generated
   `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, not `s3k-local`/
   `change-me-locally`). The first attachments run confirmed exactly this:
   `POST /attachments/upload-url` succeeded (the backend built a valid
   pre-signed URL), but every direct `PUT` to that URL got `403` from MinIO,
   failing all 24 tests in `test_attachments.py` — none of them touched by
   this checkpoint. Fixed by copying the real values from `docker inspect` into
   `backend/.env`; every attachment test, including the new Activity ones,
   then passed.

Two more issues were found only because tests could finally execute for
real, both in Checkpoint 2's own test file (not introduced this checkpoint,
and not previously catchable — Docker was unavailable in both Checkpoint 1
and Checkpoint 2):

- `test_timeline_hides_a_deal_the_rep_does_not_own` posted to
  `/crm/opportunities` without the required `stage_id`, so the deal it meant
  to create 422'd and the assertion after it failed for an unrelated reason.
  Fixed to use the file's own `_deal()` helper, which already supplies one.
- This checkpoint's own first draft of two new note-visibility tests
  (`test_account_timeline_notes_are_included_and_visibility_scoped`,
  `test_contact_timeline_notes_respect_private_visibility`) put the account
  under the *admin's* ownership and then compared what the admin vs. a plain
  rep could see — conflating "can this caller see the note" with "can this
  caller see the account at all" (accounts are owner-scoped; a rep with no
  `VIEW_ALL` cannot see an admin-owned account regardless of any note on it).
  Fixed by having the *rep* own the account/contact and the *admin* author the
  note, isolating the variable the test actually means to check.

### Environment limitations

- MinIO (attachments) and the outbox/event dispatcher (email delivery) were
  both exercised for real this checkpoint, including the full pre-signed
  `PUT`/`HeadObject`/`GET`/`DeleteObject` round trip in `test_attachments.py`
  (all 24 tests, not just this checkpoint's two new ones) once its credential
  mismatch (above) was fixed, and a real (stubbed-provider) outbox drain in
  `test_a_sent_email_joins_the_timeline...`. Nothing storage- or
  delivery-related was skipped.
- **The Browser preview tooling still cannot reach this worktree** — the same
  session-level mismatch documented in Checkpoints 1–2 (`preview_start`
  resolves `.claude/launch.json` against the worktree this session was
  *launched* in, not the one entered mid-session via `EnterWorktree`).
  Verification of the new UI (the Timeline sections on Contact/Opportunity,
  the follow-up flow, the Tasks quick-views, Leads drag-and-drop) is
  therefore static only: `tsc`, `eslint`, `next build`, and manual code
  review — no screenshot, no live click-through. **Recommended before
  trusting this checkpoint's frontend in production:** open a Contact and an
  Opportunity in a real browser and confirm the new Timeline section renders;
  log a completed call and use "Create follow-up"; try the Tasks quick-view
  row; drag a Leads card between columns and confirm a drop onto `CONVERTED`
  reverts with the backend's message.
- Activity-level attachments (#26) have no frontend surface — there is no
  activity detail page to host an `AttachmentsPanel` on. The capability is
  enabled and tested at the API layer only; documented as a gap, not hidden.
- Nothing above was faked or assumed to pass.

### Accidental-change / secret check

- `git diff --stat` scoped to the files named above plus this progress file
  (27 modified, 4 new); nothing unrelated touched.
- Diff scanned for credential-shaped strings; none found. `backend/.env` (the
  local, gitignored placeholder file whose `DATABASE_URL` port was corrected)
  is not tracked by git and is not part of this commit.
- `git diff --check`: no whitespace errors (only pre-existing LF→CRLF
  conversion notices, not errors).

## Checkpoint 4 — Completed (2026-09-11)

Audited the form-builder/customization/editing surface named in the brief
before writing anything: custom fields (Phase E), picklists, saved views'
unused `columns` column, and the Kanban boards' native-HTML5-DnD pattern were
all already solid and reused rather than rebuilt. What the audit found
genuinely missing was a real layout/section/rule model behind "form builder"
(there was none — custom fields rendered in definition order with no
grouping), actual drag-and-drop (the only DnD in the app was the two Kanban
boards), any server-enforced conditional field logic, and inline/bulk editing
UI (the backend's single-record `PATCH` endpoints existed but nothing called
them from a table cell or a multi-select action).

### What was already there (extended, not rebuilt)

- `crm.custom_fields.*` (Phase E) — `CustomFieldDefinition`, per-type
  validation, `CustomFieldValueService.resolve()`/`_require_present()`. The
  layout system extends this service (a `record_context` parameter, a
  `_layout_overrides()` hook) rather than duplicating field validation.
- `crm.saved_views.columns` (Phase F) — already a JSONB column on `SavedView`,
  written by nothing and read by nothing. `SavedViewPicker` now actually
  round-trips it; no schema change was needed.
- `FE/components/crm/kanban/KanbanBoard.tsx`'s native HTML5 drag-and-drop
  (Checkpoints 2–3) — the duplicate-submission fix (#54) widened its existing
  `onCardDrop` contract rather than replacing the drag mechanism.
- Every entity's single-record `PATCH`/state-machine endpoints
  (`update_open`, `change_status`, `change_stage`, …) — inline editing and
  bulk editing both call these directly, one record at a time, so every
  permission check, `RecordVisibility` scope, and Blueprint/state-machine rule
  they already enforce applies identically whether the call came from one
  record's detail form, a table cell, or a bulk action.
- `imports/*` (existing CSV pipeline) — extended with `custom:` mapping
  targets and mapping templates rather than a second importer.

### What was built

**Backend — new module, `backend/app/products/crm/layouts/`:**
- `models.py` — four tables: `RecordLayout` (per org+entity_type,
  DRAFT/PUBLISHED, a partial unique index enforcing at most one published
  layout per org+entity_type), `LayoutSection` (name, position, 1–2 columns),
  `LayoutField` (`field_key` — either a built-in name like `"status"` or a
  `"custom:<api_name>"` reference — position, column span, visibility,
  required/read-only overrides, label/help/placeholder overrides),
  `LayoutFieldRule` (target field key, AND/OR logic, a JSONB condition list,
  visibility/required effects, position for precedence). Rule targets are
  restricted to placed custom fields only — see Known limitations.
- `catalog.py` — `builtin_field_names(entity_type)` derives the built-in
  fields a layout may reference from each entity's `*Response` Pydantic
  schema (not its `*Create` schema — condition-driver fields like `status`
  and `stage_id` are server-managed and never appear on a Create schema, and
  the brief's own worked example, "IF Lead Status = Qualified," needs exactly
  this field).
- `evaluate.py` — pure, DB-free rule evaluation: 10 operators, AND/OR
  combination, and `effective_custom_field_states()` implementing the
  precedence base → matching rule (position order, later wins) →
  hidden-implies-not-required (applied last, always). Reused unmodified by
  both the publish-time validator and the runtime enforcement path, so the
  admin's preview evaluates the identical function the server later enforces.
- `repository.py`, `service.py`, `schemas.py`, `router.py` — full CRUD +
  publish/unpublish + reorder + evaluate REST API at `/crm/layouts`, gated by
  a new `record_layouts` permission module (Admin: full; Manager/User:
  VIEW-only, matching Blueprints' own default).

**Backend — server-side conditional enforcement (the part that cannot live
only in the browser):**
- `shared/custom_field_hook.py`, `custom_fields/service.py` — `resolve()` and
  `_require_present()` now accept a `record_context` (the record's current
  and about-to-be-written built-in field values) and consult the *published*
  layout's rules — via a lazy, function-body import of `layouts.evaluate`/
  `repository` to avoid a module-level circular import between `custom_fields`
  and `layouts` (`layouts.service` imports `custom_fields`) — before deciding
  whether a custom field is required. A client cannot mark a field "not
  required" by hiding it in its own request: the server re-derives visibility
  and required-ness from the record's actual stored/submitted state on every
  write, independent of anything the request claims.
- `shared/service.py` — `TenantScopedService.create()`/`update()` build this
  `record_context` from the payload (create) or from a new
  `_built_in_snapshot()` merged with the touched fields (update) and thread it
  through; `_require_present()`'s enforcement therefore runs on every create
  and update of a layout-scoped entity, not only through the layout builder's
  own preview.
- Centerpiece test:
  `test_layouts.py::test_conditional_required_is_enforced_server_side_on_write`
  — creates a lead, edits its custom field while `status=NEW` (rule not yet
  active, succeeds), transitions the lead `NEW→CONTACTED→QUALIFIED` through
  the real status-change endpoint, then confirms clearing the now-required
  custom field is rejected with `422` naming the field, and that supplying a
  value succeeds. Unpublishing the layout stops enforcement (also tested).

**Backend — bulk operations:**
- `shared/service.py` — `bulk_update()`/`bulk_delete()` on
  `TenantScopedService`, looping per id through `get_or_404` +
  `update`/`soft_delete` (an overridable `_bulk_update_one()` hook lets an
  entity keep its own single-record rules — e.g. Opportunities route bulk
  edits through `update_open` so a closed deal is refused exactly as a normal
  edit would be), collecting a `BulkOperationResult` (succeeded ids + a
  reason per failed id — never a silent partial write).
- `leads`, `opportunities`, `contacts`, `accounts` — each gained
  `POST /bulk-update`, `/bulk-delete`; Leads gained `/bulk-status`
  (`bulk_change_status`, looping the real `change_status` state machine per
  record) and Opportunities gained `/bulk-stage` (`bulk_change_stage`,
  looping the real `change_stage`/Blueprint-validated transition per record).
  An illegal transition or a permission refusal on one record in a batch is
  reported as that record's failure, never silently dropped or silently
  applied to the rest.
- `shared/schemas.py` — `BulkOperationFailure`, `BulkOperationResult`,
  `BulkIdsRequest`, shared by every entity's bulk endpoints.

**Backend — CSV import + field mapping:**
- `imports/catalog.py` — a mapping target can now be `custom:<api_name>`,
  resolved against the org's active `CustomFieldDefinition`s
  (`custom_field_targets()`/`is_custom_field_target()`).
- `imports/service.py` — `_map_row()` routes `custom:`-prefixed targets into
  a nested `custom_fields` dict passed to the entity's own create path, so a
  mapped custom field is validated by the same `CustomFieldValueService` any
  other write goes through — a required custom field left unmapped fails only
  that row, not the whole file; an unknown `custom:` target is refused before
  the file is even read.
- `imports/models.py` (new), `service.py`, `router.py`, `schemas.py` —
  `ImportMappingTemplate` (entity slug, name, mapping JSON, duplicate policy)
  + `ImportMappingTemplateService` (name-uniqueness and per-entity count
  limit) + `GET/POST /crm/imports/{slug}/mapping-templates`,
  `DELETE .../{id}`.
- Fixed in passing (a pre-existing bug surfaced by this work, not introduced
  by it): the mapping dropdown always offered a raw `custom_fields` JSONB
  column as a target, which could never validate against a CSV cell (a string
  can't satisfy a dict-shaped column) — every row mapped to it failed. Removed
  from the mapping options, the auto-suggest map, and the downloadable
  template header in `imports/router.py` and `frontend/features/crm/imports`.

**Frontend — Layout Builder:**
- `features/crm/layouts/` — typed API client mirroring the backend schemas;
  `evaluate.ts`, a TypeScript port of the backend's pure evaluator (same
  operators, same precedence) used for the builder's live preview so what the
  admin sees while configuring matches what the server will enforce.
- `components/crm/layouts/LayoutCanvas.tsx` — `@dnd-kit`-based drag-and-drop
  (the library decision deferred twice through Checkpoints 2–3, made once
  here as planned, since it is needed for field ordering, sections, and later
  dashboard widgets simultaneously): drag a field to reorder it or move it
  between sections, persisted immediately via
  `POST /layouts/{id}/fields/reorder`; a failed request reloads from the
  server (the same optimistic-then-reconcile pattern the custom-fields admin
  screen's own reorder buttons already used).
- `components/crm/layouts/FieldConfigDrawer.tsx` — per-field settings
  (label/help/placeholder overrides, column width, required/visible/
  read-only) and a rules editor (operator, AND/OR, conditions, visibility/
  required effects), with unsaved-changes confirmation on close.
- `components/crm/layouts/LayoutPreview.tsx` — renders the real custom-field
  input components (not a mock), reactive to simulated field values via
  `effectiveFieldStates`, so an admin can verify a rule live while building it.
- `app/(crm)/admin/layouts/page.tsx` — the builder's top-level page: entity
  selector, layout list/create, publish/unpublish (confirmed), available
  fields sidebar.
- `frontend/app/(crm)/admin/page.tsx` — a "Form layouts" admin nav card.

**Frontend — conditional rendering in real forms:**
- `components/crm/forms/CustomFieldInputs.tsx` — now consults the published
  layout (`usePublishedLayout`), computes effective visibility/required state
  from the current record's live field values via the shared `evaluate.ts`,
  reorders fields to the layout's configured order (placed fields first, any
  unplaced field still appended so nothing silently disappears), hides
  `visible: false` fields, and applies label/help-text overrides. Wired with
  `recordContext={{ ...editing, ...form }}` on Leads/Opportunities/
  Contacts/Accounts (Campaigns deliberately excluded — out of layout scope).

**Frontend — list/table customization, inline and bulk editing:**
- `components/crm/tables/DataTable.tsx` — `EditableCell` (click-to-edit,
  correct control per type, Enter/blur commit, Escape cancel, a `pending`
  re-entrancy guard against double-submit, inline `role="alert"` error);
  header/row selection checkboxes; wired via new `editable`/`editType`/
  `editOptions`/`onCellEdit` column config and `selectable`/`selectedKeys`/
  `onSelectionChange` props.
- `components/crm/toolbar/BulkActionsToolbar.tsx` — "N selected" + bulk edit
  (one field/value across the selection) + bulk delete (confirmed) + an
  `extraActions` slot (Merge stays here where it already existed; Leads adds
  bulk status change, Opportunities adds bulk stage change) + clear
  selection. `reportOutcome()` renders success/partial/failure counts
  straight from the real `BulkOperationResult` — a partial failure is always
  shown as partial, never rounded up to success.
- `components/crm/toolbar/ColumnChooser.tsx` — checkbox popover toggling
  optional column visibility; wired on the Leads list next to
  `SavedViewPicker`, which now saves/restores `columns` alongside filters/sort.
- Leads/Opportunities/Contacts/Accounts list pages — replaced hand-rolled
  checkbox-select columns with `DataTable`'s built-in selection; added
  `editable` config to several columns per entity; replaced the old
  merge-only toolbar with `BulkActionsToolbar`.
- `components/crm/kanban/KanbanBoard.tsx` — `onCardDrop` may now return a
  Promise; a `pendingIds` set disables and dims a card while its own drop
  request is in flight, closing a duplicate-submission window a fast repeat
  drop could otherwise open (Leads/Opportunities boards already awaited their
  own status/stage-change calls; this makes the guard structural instead of
  relying on every caller remembering to disable the card itself).

**Frontend — CSV import:**
- `components/crm/import/ImportWizard.tsx` — mapping options show custom
  fields with a plain label and a "— custom field" suffix (via
  `fieldDisplayLabel()`); a "Saved mappings" row applies a template, and
  "Save this mapping as…" persists the current one.

### Tests

- `backend/tests/unit/test_layout_evaluate.py` (new, 35 tests) — every
  operator, AND/OR combination, precedence ordering, hidden-implies-
  not-required, and the `_as_text(None)` empty-string fix. All pass.
- `backend/tests/integration/test_layouts.py` (new, 12 tests) — layout CRUD;
  drag-reorder persistence; unknown-field-key rejection; permission gating
  (a rep can view a published layout but not edit it); tenant isolation;
  publish refused on an empty layout; publishing demotes the incumbent
  published layout; a rule may only target a placed custom field; the
  preview endpoint reflects rule effects; the server-side-enforcement
  centerpiece test (above); unpublishing stops enforcement. All pass.
- `backend/tests/integration/test_bulk_operations.py` (new, 8 tests) — bulk
  update success and missing-id reporting; bulk update cannot change a
  lead's status (a field Pydantic silently drops from `LeadUpdate`, not a
  bulk-specific hole); bulk update cannot edit a closed opportunity; a rep
  without `VIEW_ALL` gets a colleague's lead reported as a failure, not
  silently skipped; bulk delete archives; bulk delete without `DELETE`
  permission is refused (403); bulk status change reports an illegal
  transition as a failure, not a success; bulk stage change reports a closed
  deal as a failure. All pass.
- `backend/tests/integration/test_csv_import_custom_fields.py` (new, 8
  tests) — the entity catalogue offers the org's custom fields as targets; a
  column mapped to a custom field round-trips into the created record; a
  required custom field left unmapped fails its row, not the file; an
  unknown `custom:` target is refused before the file is read; a mapping
  template can be saved, listed, and deleted; naming a template with an
  unknown field is refused; templates are isolated per entity slug. All pass.

### Static analysis

- **Ruff** (`app tests migrations`): clean.
- **mypy** (`app`, matching CI): clean, 310 source files. (Required
  converting the `RuleLike` Protocol's members to `@property` so mypy checks
  them covariantly against SQLAlchemy ORM instances — a plain-attribute
  Protocol member is checked invariantly and rejected a `StrEnum` subtype
  where a `str` was declared.)
- **Frontend `tsc --noEmit`**: clean.
- **Frontend `eslint .`**: clean. Caught three real `react-hooks/
  set-state-in-effect` violations during development (`LayoutCanvas.tsx`
  syncing `sections` from the `layout` prop, `usePublishedLayout.ts`'s
  early-return branch, `admin/layouts/page.tsx` resetting state ahead of an
  async fetch) — all fixed using this codebase's two established patterns:
  the "stamped-result" pattern (tag an async result with the request
  identity it answers, compare at read time) for the two data loads in
  `page.tsx`, and "render-time adjustment" (compare the prop/derived value
  directly in the render body and `setState` there, not in a `useEffect`)
  in `LayoutCanvas.tsx` and for deriving the selected layout id in `page.tsx`.
- **Frontend `next build`**: succeeds; all 54 routes generate, including the
  new `/admin/layouts`.
- **Backend `pytest tests/unit tests/integration`** (full regression, run
  against a clean, freshly migrated, throwaway PostgreSQL —
  `checkpoint4_test`, dropped and recreated from zero, all 27 migrations
  reapplied in order — plus real MinIO and Redis, the same Docker stack
  Checkpoint 3 brought up): **1844 collected, 1843 passed, 1 failed.** The
  run was executed in full, not a subset, and includes every pre-existing
  suite (tenant isolation, RBAC, Blueprints, dashboards, saved views, merge,
  attachments, audit logging, and Checkpoints 2–3's own tests) alongside this
  checkpoint's 63 new tests, none of which failed. The one failure —
  `test_tenant_switching.py::test_a_dual_member_still_cannot_reach_an_organization_they_do_not_belong_to`
  (asserted `403`, got `401`) — is in a file untouched by this or any prior
  checkpoint (unchanged since the very first commit on this branch, verified
  with `git diff` against the branch base), passed cleanly (9/9) when
  re-run alone immediately after, and is not reproducible in isolation — a
  pre-existing timing-sensitive flake under full-suite load, not a
  regression introduced here. Reported honestly rather than silently
  re-run until green.

  Two earlier full-suite attempts this session produced much larger, clearly
  spurious failure counts; both were diagnosed, not ignored, before this
  clean run: a background test process resumed from before this session's
  context was continued was still alive and — unknown at the time — still
  hitting the same `checkpoint4_test` database when a second, independent
  full run was started, and a leftover `uvicorn` dev server from this
  checkpoint's live-browser verification was also holding connections to
  the same database throughout. Both were stopped, zero lingering sessions
  on the database were confirmed, the database was dropped and rebuilt from
  a clean migration, and the run above is the result of the single,
  uncontended pass that followed.

### Security validation

- **Tenant isolation:** every new table (`record_layouts` and its three
  children, `import_mapping_templates`) has PostgreSQL row-level security
  forced on, matching the rest of the schema; `test_layouts.py` and
  `test_csv_import_custom_fields.py` each include an explicit
  cross-tenant-cannot-see test.
- **RecordVisibility / RBAC:** layout CRUD is gated by the new
  `record_layouts` permission module (Admin full, Manager/User VIEW-only);
  bulk operations call each entity's own single-record path per id, so
  `VIEW_ALL`/`EDIT_ALL`/`DELETE` scoping applies per record inside a batch,
  not once for the whole batch — a rep bulk-editing five records they own and
  one they don't gets four successes and one reported failure, never five
  successes and a silent drop.
- **Server-side authority for conditional logic:** the browser's rule
  evaluation (`evaluate.ts`) exists only for the builder's live preview and
  a form's responsive show/hide; the backend independently re-evaluates the
  identical rules (`evaluate.py`, the same precedence) from the record's
  actual stored/submitted values on every create and update, so no
  client-controlled flag can mark a field "not required" — proven by the
  centerpoint test above, not merely asserted.
- **Blueprint/state-machine integrity under bulk and drag operations:** bulk
  status/stage change and the Kanban boards' drag-and-drop all call the
  entity's one real transition function; no new code path bypasses
  `change_status`/`change_stage`'s existing Blueprint validation.
- **No silent partial writes:** `BulkOperationResult` makes every bulk
  endpoint return both the succeeded ids and a reason per failed id; the
  frontend's `reportOutcome()` always surfaces both counts.

### Known limitations

- **No per-role layout assignment.** One published layout applies to every
  viewer of an entity type; there is no "this layout for Sales Rep, that one
  for Manager." Flagged explicitly in the feature-audit table (#41) as 🟡,
  not claimed as ✅.
- **Layout rules can only target custom fields, not built-in fields.** A
  condition can reference either a built-in or a custom field, but a rule's
  *effect* (visible/required) may only be attached to a custom field — the
  DB constraint `target_field_key must be custom:-prefixed` enforces this
  deliberately, since built-in field requiredness is owned by each entity's
  own Pydantic `*Create`/`*Update` schema, not by the layout system, and
  layering a second required/visible authority over an already-authoritative
  one would create two sources of truth for the same built-in field.
- **Built-in field rendering in production forms is not layout-driven.**
  `CustomFieldInputs.tsx` (the custom-field block) fully respects the
  published layout's order, visibility, required-overrides and label
  overrides; each entity's hardcoded built-in-field JSX (name, email, status,
  …) does not — a layout's sections/ordering apply only to the custom-field
  portion of a form, not the whole form. Replacing every entity's built-in
  form JSX with a layout-driven renderer is a larger, separate change,
  flagged rather than attempted partially.
- **Column chooser is wired on Leads only.** Accounts, Contacts and
  Opportunities' tables still show a fixed column set; `SavedView.columns`
  round-trips everywhere the picker is used, but only Leads exposes the
  chooser UI itself (#46, 🟡).
- **"Add to campaign" and "export selected" bulk actions were not built**
  (#49 stays 🟡); export remains all-matching-filter, not selection-scoped.
- **Opportunities are still not an importable CSV entity** (pre-existing gap,
  unchanged this checkpoint — #50 stays 🟡 for that one reason, custom-field
  mapping itself is now complete).
- **Import mapping templates are per entity slug**, not shareable across
  entities (e.g., a Leads mapping cannot be reused for Contacts import).
- Campaigns are deliberately excluded from layout scope — no
  `LAYOUT_ENTITY_TYPES` entry, no `recordContext` wiring — since the brief
  scoped the form builder to Account/Contact/Lead/Opportunity.
- Nothing above was faked or assumed to pass; each is either a documented
  design boundary (built-in vs. custom field targets, per-role assignment
  deferred) or a scope line this checkpoint chose not to cross to stay
  finishable and testable.

### Environment / verification notes

- Docker (`s3k-postgres` on port 5434, `s3k-minio`, `s3k-redis`) was already
  up from Checkpoint 3 and stayed up for this checkpoint — a throwaway
  `checkpoint4_test` database (owned by the existing `s3k_app` role) was
  created and migrated from a bare `postgres` head, exactly Checkpoint 3's
  pattern, leaving the shared `s3k_app` database untouched.
- Unlike Checkpoints 1–3, the Browser preview tooling *did* reach this
  worktree this session, so this checkpoint's new UI was verified live, not
  only statically: the Layout Builder (creating a layout, adding sections,
  dragging fields between them, configuring a conditional rule, publishing,
  and watching the live preview react), the resulting conditional field on a
  real Lead's edit form, inline cell editing (save/cancel, validation error
  path), bulk edit and bulk delete with a real multi-record selection, bulk
  lead-status and bulk opportunity-stage change (including one illegal
  transition correctly reported as a per-record failure), Kanban drag-drop
  with the new pending-card guard, the CSV import wizard's custom-field
  mapping and saved-template flow, and the Leads column chooser. Three
  issues were found and fixed only because of this — see the Errors-and-
  fixes notes captured during the session: a synthetic-click quirk on one
  button (worked around with `element.click()` instead of coordinate
  clicks), two `document.querySelectorAll('select')` index mismatches in the
  verification scripts themselves (not product bugs — re-diagnosed by
  reading each matched element's value), and one genuine, small,
  pre-existing product bug (the always-invalid `custom_fields` CSV mapping
  target, fixed above) surfaced by, not introduced by, this checkpoint's
  work.
- A double-PATCH was observed firing from one inline-edit save action during
  browser-automation testing; root cause not fully pinned to product code
  vs. a synthetic-click artifact, so fixed defensively regardless (the
  `pending` re-entrancy guard in `EditableCell`) since it protects a real
  user's accidental fast double-click either way.

### Accidental-change / secret check

- `git status --short` reviewed against the file list above: every modified
  and new file is one this checkpoint intentionally touched; nothing
  unexplained.
- `backend/.env` and `frontend/.env.local` (both created this checkpoint,
  purely to point the local backend/frontend at the throwaway test database
  and each other for verification) are gitignored and untracked — confirmed
  via `git status` before staging.
- Diff scanned for credential-shaped strings; none found in any tracked file.
- `git diff --check`: no whitespace errors.

## Checkpoint 5 — Completed (2026-09-12)

Audited the search/report/dashboard surface named in the brief before writing
anything, and found it far more built than the pre-checkpoint audit table
suggested: global search already covered four entities with real tsvector
ranking and record-visibility narrowing; the reports module already had nine
built-in catalogue reports, folders, sharing and periods, with its own module
docstring explicitly foretelling a builder as "a further definition kind,"
layered on rather than replacing the reviewed-code catalogue; dashboards
already had a configurable-board system (tiles, sharing, per-viewer
rendering) with a whole-list reorder endpoint already in place. The
checkpoint's real gaps were narrower than "build search/reports/dashboards
from scratch": a real ad-hoc report builder, a reusable multi-condition
AND/OR filter engine, dashboard-wide date filtering, dashboard drag-and-drop,
a fifth searchable entity, and a handful of named executive-dashboard metrics
nothing yet computed (weighted pipeline chief among them). This checkpoint is
concentrated on exactly those.

### What was already there (extended, not rebuilt)

- `BE/search/*` — full-text + trigram global search across four entities,
  with `RecordVisibility` resolved *inside* the ranking query (risk R14) —
  extended to a fifth entity (activities) using its exact existing pattern
  (`Computed(...)` generated column, GIN + trigram index, one more
  `MODULE_FOR_TYPE`/`MODEL_FOR_TYPE`/`_display_name`/`_subtitle` case), not a
  parallel search mechanism.
- `BE/reports/{catalog,models,library,service,router}.py` — the nine
  built-in reports, `SavedReport`/`ReportFolder`, sharing, periods. The
  custom-report engine (below) is additive to this exact table and this
  exact `run_saved` dispatch, not a second reporting stack: a custom report
  is still a `SavedReport` row, still goes through folders/sharing/periods,
  still runs through `resolve_period`.
- `BE/dashboard/{models,library,router}.py` — configurable boards, tiles
  pointing at a saved report, per-viewer rendering (`render()` runs every
  tile as the caller, a tile the viewer cannot read comes back marked
  `unavailable` rather than failing the page), and a whole-list
  `PUT .../layout` reorder endpoint already built for exactly what
  Checkpoint 5's drag-and-drop needed to call.
- `FE/components/crm/charts/MiniCharts.tsx` — the project's own
  dependency-free bar/line/donut/funnel components, reused for every new
  chart in this checkpoint (report builder preview, dashboard revenue trend,
  pipeline-by-owner, lead-source-performance) — no charting library added.
- `@dnd-kit` — adopted in Checkpoint 4 for the layout builder, reused here
  for dashboard tile reordering rather than a second drag library or native
  HTML5 drag-and-drop.
- `custom_fields/filters.py`'s `FilterOperator` — the 10-operator,
  per-type-legal vocabulary for a JSONB custom field. The new
  `reports.conditions.ReportFilterOperator` (12 operators, over *built-in*
  typed columns) maps onto it exactly where the two overlap, so a `custom:`
  condition inside an advanced filter or a custom report is translated
  straight through to `custom_field_filter` rather than a second
  implementation of custom-field filtering.

### What was built

**Backend — the shared filter/report engine (`backend/app/products/crm/reports/`):**

- `fields.py` (new) — the allow-list everything else is built on: a
  `ReportEntity` enum (LEAD/CONTACT/ACCOUNT/OPPORTUNITY/ACTIVITY) and a
  `ReportField` registry per entity naming a real SQLAlchemy column (with an
  optional `JoinSpec` for a joined field — `stage`/`account`/`lead_source`),
  its `ColumnType`, and which of filter/group/sort/aggregate it supports. A
  field a report touches is always resolved through this registry — never a
  column name taken off a request and interpolated into SQL.
- `conditions.py` (new) — `ReportFilterOperator` (eq/ne/contains/
  starts_with/ends_with/gt/gte/lt/lte/between/in/is_empty/is_not_empty),
  `ReportCondition`/`ReportFilterGroup` (one AND/OR level over a flat
  condition list — the same shape `layouts.evaluate`'s rule conditions
  already proved sufficient for), and `build_condition`/`combine`, the one
  place a condition becomes a SQLAlchemy predicate — over a built-in typed
  column directly, or over a custom field by delegating to
  `custom_field_filter`. A relative-date value (`{"relative": "THIS_QUARTER"}`)
  resolves through the *exact* `resolve_period` a saved report's own stored
  period already goes through.
- `custom.py` (new) — `CustomReportEngine`: validates a definition
  (`validate_definition`) without running SQL, then runs it under the
  identical four-step model `reports/service.py` documents for the
  catalogue (resolve → authorize on the entity's own module → resolve
  `RecordVisibility` → aggregate inside PostgreSQL, never in Python).
  Two output shapes from one definition: **row-listing** (selected built-in
  fields, capped at `MAX_REPORT_ROWS`) or **grouped** (`GROUP BY` a field or
  a `date_trunc` bucket, with `count`/`sum`/`avg`/`min`/`max` aggregations
  and an optional chart hint) — never both, matching
  `CustomReportDefinition._shape_is_coherent`'s own either/or validation.
  Also `build_advanced_filter_predicate`, the standalone entry point the
  four list endpoints (below) and a saved view's advanced filter both call —
  the same condition/group machinery, reused rather than re-implemented a
  third time.
- `schemas.py` — `CustomReportDefinition`, `ReportCondition`/
  `ReportFilterGroup` (re-exported from `conditions.py`), `ReportAggregation`,
  `AvailableFieldInfo`, `CustomReportPreviewRequest`; `SavedReportCreate`/
  `Update`/`Response` extended with an optional `custom_definition` and a
  model validator requiring exactly one of it or `base_report_key`.
- `models.py` — `SavedReport.base_report_key` is now nullable,
  `custom_definition` (JSONB) added, with a CHECK constraint
  (`(base_report_key IS NOT NULL) != (custom_definition IS NOT NULL)`) that
  holds even for a row written outside the API.
- `library.py` — `create_saved`/`update_saved` validate a custom definition
  the same way a catalogue key is validated; `run_saved` branches to
  `CustomReportEngine.run` for a custom report and gained a `date_override`
  parameter (for the dashboard date filter, below) that replaces rather than
  combines with the stored period; a `CannotChangeReportKindError` (409)
  refuses a PATCH that would turn a catalogue report into a custom one or
  back — a saved report's kind is closer to its type than to one of its
  fields, and every dashboard tile pointing at it assumes that does not
  change.
- `router.py` — `GET /crm/reports/custom/fields?entity=` (the field registry,
  for the builder — not permission-gated on its own, the same "which reports
  exist is the answer" reasoning `GET /crm/reports` already documents) and
  `POST /crm/reports/custom/preview` (run an unsaved definition — the
  builder's preview step), both declared before `/{key}/run` for the same
  routing reason `/saved` and `/folders` already are.

**Backend — advanced filtering on list endpoints (additive):**

- `shared/advanced_filter_query.py` (new) — `parse_advanced_filter`, a
  FastAPI dependency parsing `?advanced_filter=<json ReportFilterGroup>`
  into a validated Pydantic object, shared by every list endpoint that
  offers it.
- `leads/router.py`, `contacts/router.py`, `accounts/router.py`,
  `opportunities/router.py` — each `list_*` gained the `advanced` dependency
  and, when present, ANDs `build_advanced_filter_predicate(...)`'s result
  into the *existing* filter list — purely additive, the named query
  params (`?status=`, `?owner_id=`, `cf_*`) and every existing test keep
  working with the parameter simply omitted.

**Backend — saved-view advanced filter (additive):**

- `views/models.py` — `SavedView.advanced_filter` (nullable JSONB), stored
  *alongside* the existing flat `filters` column rather than replacing it —
  every view saved before this migration, and its validator, is untouched.
- `views/schemas.py` — `advanced_filter: ReportFilterGroup | None` on
  `SavedViewBase`, validated against the view's `entity_type` at create time;
  `views/service.py`'s `update_view` validates a *changed* advanced filter
  against the existing row's `entity_type` (the one point it becomes known
  on an update).

**Backend — global search, fifth entity:**

- `activities/models.py` — `search_vector` (the same `searchable()` helper
  every other entity uses), weighted `subject` (A) / `outcome` (C) /
  `description` (D).
- `migrations/20260917_0300_activity_search_vector.py` — the generated
  column, partial GIN index, and trigram index on `subject`, replicating
  `20260826_0100`'s own pattern exactly for the fifth table.
- `search/{schemas,policies,repository}.py` — `SearchEntityType.ACTIVITY`,
  its permission module (`activities` — absent from `OWNER_SCOPED_MODULES`,
  so unrestricted once the `activities.VIEW` gate passes, the same rule
  `activity_by_owner` already documents), its model, its display name
  (`subject`) and subtitle (`type` — always set, unlike `outcome`, which is
  empty for most of an activity's life).

**Backend — dashboard executive metrics and date filter:**

- `dashboard/repository.py` — `sum_weighted_pipeline_value` (open pipeline
  at each deal's own `win_probability`, `coalesce(..., 0)` for an unset one
  — never a guessed 0% or 100%), `sum_won_revenue` (trailing window),
  `lead_conversion_rate`, `won_revenue_by_month` (`date_trunc('month', …)`,
  zero-filled across the requested span), `pipeline_by_owner`.
- `dashboard/service.py` — wires the above into `summary()`, and reuses
  `ReportRepository.lead_conversion_by_source` directly (imported and called,
  not re-queried) for `lead_source_performance` — the dashboard number and
  the report's own number can never disagree.
- `dashboard/schemas.py` — `DashboardKpis` gained `weighted_pipeline_value`,
  `won_revenue`, `lead_conversion_rate`; `DashboardSummary` gained
  `revenue_trend`, `pipeline_by_owner`, `lead_source_performance`;
  `DashboardComponentData` gained `date_filter_applied`.
- `dashboard/library.py`'s `render()` and `router.py`'s
  `GET .../data?date_from=&date_to=` — a dashboard-wide date override,
  applied per tile only when that tile's report actually has a date
  dimension (a catalogue report with `accepts_date_range`, or any custom
  report, which always has one); a tile with none renders its normal numbers
  unaffected, and `date_filter_applied` tells the UI which happened. Never
  persisted — the same "resolved fresh, not cached" rule a saved report's
  own period already follows.

**Frontend — the report builder:**

- `features/crm/reports/custom.ts` (new) — types and API client mirroring
  the backend schemas exactly (`ReportEntity`, operators, `ReportFilterGroup`,
  `CustomReportDefinition`, `listCustomFields`, `previewCustomReport`).
- `components/crm/reports/FilterEditor.tsx` (new) — the AND/OR condition
  editor, extracted as a **shared** component precisely so the report
  builder and the list-screen advanced filter (below) are the same UI over
  the same document, not two that could drift.
- `components/crm/reports/ReportBuilder.tsx` (new) — module → row-listing or
  grouped-and-summarised → fields/group-by/aggregations → filters (via
  `FilterEditor`) → sort → chart → Preview (rendering through the *existing*
  `ReportChart`/`ReportTable` — no change needed there, since a custom
  report's result is the identical `ReportResult` envelope a catalogue
  report already produces) → Save. Uses the stamped-result pattern for its
  field-registry fetch (`fieldsResult` tagged with the entity it answers)
  rather than resetting state synchronously in the load effect, matching
  this codebase's established `react-hooks/set-state-in-effect` avoidance.
- `app/(crm)/reports/page.tsx` — a "New custom report" entry point and,
  on a custom saved report, an "Edit shape" action reopening the builder
  pre-filled; saving a new one hands off into the *same* name/folder/
  period/visibility drawer a catalogue report is saved through (a custom
  report has a period too — `date_field` is exactly what it narrows).

**Frontend — advanced filtering on list screens:**

- `components/crm/toolbar/AdvancedFilterBar.tsx` (new) — a popover wrapping
  the shared `FilterEditor`, translating the built group into
  `?advanced_filter=<json>` on Apply (not on every keystroke — an advanced
  filter is assembled and committed, not typed live). Wired onto
  Leads/Contacts/Accounts/Opportunities, additive alongside each page's
  existing search box and named filters.

**Frontend — global search:**

- `features/crm/search/index.ts`, `components/crm/topbar/CommandPalette.tsx`
  — `ACTIVITY` added to `SearchEntityType`/`ENTITY_LABELS`/`ENTITY_ICONS`;
  `hitHref` returns `null` for an activity (no detail page exists to open —
  see Known limitations), and the palette renders such a row as
  found-but-not-navigable (no arrow, `aria-disabled`) rather than pretending
  a destination exists.

**Frontend — dashboards:**

- `app/(crm)/dashboard/page.tsx` (the fixed summary) — three new KPI cards
  (Weighted Pipeline, Won Revenue, Lead Conversion) and three new panels
  (Revenue Trend as a `LineChart`, Pipeline by Owner and Lead Source
  Performance as `BarChart`s), all reading the enriched summary payload.
- `app/(crm)/dashboards/[id]/page.tsx` (configurable boards) — tile drag
  reordering via `@dnd-kit` (`DndContext`/`SortableContext`/`useSortable`,
  `rectSortingStrategy` for the 12-column flow), calling the *same*
  `reorderComponents` the up/down buttons already called — both kept, per
  the module's own updated docstring. A `DateFilterBar` (two date inputs)
  passes `date_from`/`date_to` to `renderDashboard`; each tile shows a
  "Filtered" badge exactly when its own `date_filter_applied` says so.
- `features/crm/dashboards/index.ts`, `features/crm/dashboard/types.ts` —
  `renderDashboard` gained the optional date-filter params;
  `DashboardComponentData` gained `date_filter_applied`; `DashboardKpis`/
  `DashboardSummary` gained the new fields (`RevenueMonth`,
  `OwnerPipelineSummary`, `LeadSourcePerformance`).

### Tests

- `backend/tests/unit/test_search_permissions.py`,
  `test_search_index_agreement.py` — extended for the fifth entity
  (`ACTIVITY`): the "every view grants every type" tests updated to include
  `activities.VIEW`, a new test asserting `activities.VIEW` is required
  exactly like the other four, and the index-agreement fixture generalised
  to check each entity against *its own* migration (four against
  `20260826_0100`, activities against `20260917_0300`) rather than a single
  shared one — the same "a sixth entity added without a vector must fail
  here" tripwire the file already existed to be, now correctly spanning two
  migrations. All pass.
- `backend/tests/integration/test_search.py` — the "searched" assertion
  updated to five types; new tests for an activity found by subject and
  labelled by its own `type`. All pass.
- `backend/tests/integration/test_custom_reports.py` (new, 23 tests) —
  row-listing field selection; unknown-field 422; empty-shape 422; a
  grouped report matching the built-in `pipeline-by-stage` report's own
  numbers; missing-aggregation 422; illegal aggregation-for-type 422;
  `group_by_interval` on a non-date field 422; a month-grouped revenue trend;
  AND requires every condition, OR matches either; `between`; `starts_with`/
  `ends_with`; a relative-date condition reusing `resolve_period`; an
  illegal operator-for-type 422; a custom-field filter condition narrowing a
  report, and an unknown custom field refused at run time; available-fields
  includes custom fields and marks them `is_custom`; activities have none;
  authorization requires the entity's own module (a rep with only
  `leads.VIEW` can run a lead report, not an opportunity one); a rep and a
  manager see different totals for the identical grouped report (the phase
  gate, for the ad-hoc engine); save/run/edit-kind-refused round trips. All
  pass.
- `backend/tests/integration/test_advanced_filters.py` (new, 10 tests) —
  AND narrows, OR widens; combines with named query params without
  replacing them; malformed JSON and an unknown field are both 422; a rep
  cannot use an advanced filter to reach a colleague's record (narrows
  within `RecordVisibility`, never widens it); numeric `gte` on
  opportunities; a saved view stores and validates an advanced filter,
  rejects one naming an unknown field, and validates a *changed* one on
  update. All pass.
- `backend/tests/integration/test_dashboard.py` — extended with weighted
  pipeline (using a deal's own supplied `win_probability`, since — a genuine
  discovery while writing this test — only a stage *change*/`reopen`
  defaults `win_probability` from the stage; a freshly created deal carries
  whatever the create request gave it, which the new weighted-pipeline test
  now documents explicitly rather than assuming); an unset probability
  correctly contributing zero to the weighted figure while still counting
  in full toward the unweighted total; won revenue counting only recently
  closed-won deals; lead conversion rate as a real share; revenue trend
  zero-filled across six months with the current month's won deal correctly
  attributed; pipeline-by-owner resolving a real display name;
  lead-source-performance provably equal to the report's own answer (not
  merely similar). The pre-existing exact-dict-equality empty-state test was
  updated for the three new KPI fields and the three new list fields rather
  than left to fail. All pass.
- `backend/tests/integration/test_dashboards.py` (extended) — a dashboard-
  wide date filter narrows a date-capable tile (`date_filter_applied: true`,
  a window excluding the won deal correctly zeroes it) and leaves a tile
  with no date dimension untouched (`date_filter_applied: false`, identical
  rows with and without the filter). All pass.
- **Backend `pytest tests/unit tests/integration`** (full regression, clean
  throwaway `checkpoint5_test` database migrated from zero — all 29
  migrations, including the three this checkpoint added, applied cleanly in
  order — plus real MinIO/Redis): **1897 collected, 1897 passed, 0 failed.**
  The run was executed in full — every pre-existing suite (tenant isolation,
  RBAC, blueprints, dashboards, custom fields, saved views, merge,
  attachments, audit logging, layouts, bulk operations, CSV import, and
  every earlier checkpoint's own tests), not only what this checkpoint
  touched — and is genuinely clean: no flake, nothing re-run to get there.
- **Frontend**: no automated frontend test suite exists in this repository
  (Checkpoints 1–4 record the same); verification here is `tsc`, `eslint`,
  `next build`, and — new for this checkpoint — extensive **live browser
  verification** against the real backend rather than static analysis alone
  (see Environment/verification notes).

### Static analysis

- **Ruff** (`app tests migrations`): clean.
- **mypy** (`app`, matching CI): clean, 314 source files.
- **Frontend `tsc --noEmit`**: clean, checked after every meaningful edit
  rather than once at the end.
- **Frontend `eslint .`**: caught one real `react-hooks/set-state-in-effect`
  violation during development (`ReportBuilder.tsx`'s field-registry load
  effect resetting state synchronously) — fixed with the stamped-result
  pattern (tag the async result with the entity it answers, compare at read
  time), matching `usePublishedLayout`'s own precedent from Checkpoint 4.
  Clean after the fix, and clean on every file touched.
- **Frontend `next build`**: succeeds.

### Security validation

- **Tenant isolation:** every new/altered table (`saved_reports.custom_definition`,
  `saved_views.advanced_filter`, `activities.search_vector`) lives under the
  same RLS-forced schema as everything else; no new table was created that
  needed its own policy.
- **RecordVisibility / RBAC — the custom-report engine:** identical
  four-step model to the catalogue (resolve → authorize on the entity's own
  module → resolve visibility → aggregate in SQL under it), proven by a test
  where a rep and a manager see different totals for the same definition —
  not merely asserted.
- **RecordVisibility — advanced filtering:** additive predicates are ANDed
  into the *same* filter list `RecordVisibility` already narrows before the
  query runs; a rep cannot use an advanced filter to reach a colleague's
  record (tested explicitly — the filter narrows *within* what visibility
  already allows, it cannot widen past it).
- **No user-authored SQL:** every field a condition, a group-by, a sort, or
  an aggregation names is resolved through the `reports.fields` registry —
  an allow-list, never a column name taken off a request and interpolated.
  A `custom:` condition is the one exception by design, and it delegates to
  `custom_fields.filters.custom_field_filter`, which has carried this exact
  guarantee (bound parameters, guarded casts) since Phase E.
- **Aggregate disclosure (the reporting module's own standing risk):** a
  custom report's totals are computed from rows already narrowed by
  `RecordVisibility` inside the SQL — never filtered after the fact — the
  same rule the built-in catalogue's own module docstring states and this
  checkpoint did not relax anywhere.
- **Dashboard date filter:** an override to a tile's rendering only, never
  written to the saved report or the dashboard; a tile still runs `as the
  viewer` exactly as it did before this checkpoint.
- **`CannotChangeReportKindError`:** a PATCH cannot turn a catalogue report
  into a custom one (or back) and thereby dodge either validation path.

### Known limitations

- **A custom report's select/group/aggregate targets are built-in fields
  only.** A tenant's custom field is filterable (reusing
  `custom_fields.filters` exactly) but cannot be selected as a column,
  grouped by, or aggregated — that needs the same guarded-cast machinery
  under a second allow-list this checkpoint does not yet keep. Documented in
  the feature-audit table (#61), not silently unsupported.
- **A saved view's advanced filter does not yet round-trip through "save
  view"/"choose view."** The column, the validation, and the list-endpoint
  application all work (proven by integration tests); the list-page UI's
  "Save view" only captures the flat `filters` document today, and choosing
  a saved view does not re-populate `AdvancedFilterBar`'s draft from a
  stored `advanced_filter`. A view with one still filters correctly when
  applied server-side (e.g. via a link or a future UI); rebuilding the
  condition by hand is the only gap.
- **An activity found by search has no detail page to open.** Consistent
  with Checkpoint 3's own documented gap ("no activity detail page exists");
  `hitHref` returns `null` for one and the palette shows it as
  found-but-informational rather than broken or silently omitted.
- **No report-result CSV export was added this checkpoint.** The existing
  per-entity CSV export (accounts/contacts/leads/opportunities lists,
  Checkpoint 1–2) is unaffected and unchanged; exporting a report or
  dashboard tile's own rows to CSV remains a gap, not newly introduced by
  this checkpoint.
- **`CRM analytics` (#66) stays partial.** A real trend over time
  (`revenue_trend`) now exists, and the report builder can construct further
  ones without new backend code, but forecasting and targets/quotas are
  still not implemented.
- **Dashboard-wide date filtering is date-only.** The checkpoint brief also
  names owner/team/stage/source as possible dashboard-wide filters; only
  date was built, because it is the one dimension every report kind
  (catalogue with `accepts_date_range`, or any custom report) already has a
  uniform answer for — an owner filter would need every one of the nine
  catalogue reports to grow a new parameter, which is materially more
  surface than this checkpoint's date-only scope. Documented rather than
  attempted partially.
- Nothing above was faked or assumed to pass; each is a stated design
  boundary or a scope line this checkpoint chose not to cross, not a gap
  discovered after the fact.

### Environment / verification notes

- Docker (`s3k-postgres` on port 5434, `s3k-minio`, `s3k-redis`) was already
  up from Checkpoint 4 and stayed up; a throwaway `checkpoint5_test`
  database (owned by the existing `s3k_app` role) was dropped and recreated
  from zero partway through the session after discovering two backend test
  runs — one resumed from before this session's context was continued, one
  started fresh without realising the first was still alive — were both
  hitting the same database concurrently, producing large, spurious,
  contention-shaped failure counts in both. Diagnosed (not ignored): both
  processes stopped, zero lingering database sessions confirmed, the
  database rebuilt and re-migrated from a clean `alembic upgrade head`, and
  every test result reported in this section is from the single,
  uncontended run that followed.
- **Real, extensive live-browser verification was performed against the
  real backend** — new for this checkpoint, and beyond what Checkpoints 1–4
  achieved. A throwaway signup/organization was created (through the actual
  `/auth/signup` and `POST /organizations` endpoints, not seeded via SQL),
  and every major feature this checkpoint built was exercised end to end in
  a real browser against real Postgres: the report builder (switching
  entity, switching row-listing ↔ grouped mode, adding a summarisation,
  choosing a chart, previewing, saving, and the saved report appearing with
  a correct "Edit shape" affordance); the dashboard summary's three new KPI
  cards and three new panels, first in their real empty states and then
  with seeded data showing correct arithmetic (a $50,000 deal at 10% stage
  probability weighing $5,000; a won deal correctly counted in won revenue
  and the revenue trend's current month); the advanced filter bar on the
  Leads list, confirmed via the actual network request that the applied
  filter's JSON matched the UI and that the result correctly narrowed to
  the one matching record; the dashboard date filter, confirmed against
  three simultaneous tiles that a date-capable custom report and a
  date-capable catalogue report both showed "Filtered" and zeroed
  correctly for an excluding window while a non-date-capable catalogue
  report showed no badge and identical numbers with and without the
  filter; dashboard drag handles rendering in Arrange mode alongside the
  pre-existing up/down buttons, and a button-driven reorder still working
  correctly against the refactored reorder code path; and global search
  finding a newly created activity, labelling it by its own type, and
  rendering it as non-navigable rather than broken. Two environment quirks
  were found and worked around, not treated as product bugs: the backend
  dev server (port 8001) had exited hours earlier from a previous session
  and needed restarting before the browser could reach it; and coordinate-
  based clicks on the advanced-filter popover twice landed on an unrelated
  sidebar link because the popover rendered below the visible preview
  viewport — worked around with `element.click()` via direct DOM queries,
  the same class of synthetic-click workaround Checkpoint 4's own notes
  describe.

### Accidental-change / secret check

- `git status --short` reviewed against the file list above: every modified
  and new file is one this checkpoint intentionally touched.
- `backend/.env` (already gitignored, its `DATABASE_URL` repointed at
  `checkpoint5_test` for this checkpoint's testing) and `frontend/.env.local`
  remain untracked — confirmed via `git status` before staging.
- Diff scanned for credential-shaped strings; none found in any tracked file.
- `git diff --check`: no whitespace errors.

## Checkpoint 6 — Completed (2026-09-12)

**Starting commit:** `d7704ad` (Checkpoint 5, on `claude/crm-zoho-gaps`). The
worktree assigned for this checkpoint had been branched from the stale
prototype line (`origin/main`) rather than from the real work; before writing
any code this session fast-forwarded its branch to
`claude/crm-checkpoint-4-forms-f097a3` at `d7704ad` — a pure fast-forward with
zero divergent commits, confirmed via `git log <branch>..HEAD` returning
empty before the move — to land on the actual Checkpoint 5 completion point
the task brief described. No Checkpoint 1–5 work was redone or reverted.

### Audit (Step 1) — before any code

`PF/events/*` (the transactional outbox, ADR-013) and the ARQ worker
(`backend/app/worker.py`) were real and already draining reminders and
outgoing email. Nothing in the codebase evaluated a rule against a record
change: every entity write path (`shared/service.py: TenantScopedService.create`/
`update`, and the guarded `LeadService.change_status`/`OpportunityService.change_stage`)
enqueued **no** event at all — the outbox existed, but nothing fed it from a
plain record write. Blueprints (`BE/blueprints/*`) were complete but
validation-only, with no concept of an *action* triggered by a transition.
Notifications (`PF/notifications/*`) had a real in-app mailbox and a
`ReminderSource` registry, but nothing rule-driven could write to it besides
the two existing reminder kinds. The condition/operator vocabulary needed for
"IF" already existed twice, independently: `reports/conditions.py` (a
SQL-predicate builder, unusable against one in-memory record) and
`layouts/evaluate.py` (a pure, DB-free evaluator against a record's current
field values — exactly the shape a workflow condition needs). This checkpoint
reused the latter rather than building a third vocabulary.

### What was built

**Trigger delivery — one generic hook, not nine.** `shared/service.py`'s
`create()`/`update()` now call `_enqueue_record_event`, which publishes
`crm.record.event_occurred` in the *same transaction* as the write — the
outbox's own guarantee, unmodified. The event names only identifiers, plus a
delta of the fields actually touched (`{field: {before, after}}`, computed
from raw column values, never the audit trail's masked/summarised copy) —
enough for a `FIELD_CHANGED` trigger to ask "did it become X," never a stale
snapshot of the whole record. `LeadService.change_status` and
`OpportunityService.change_stage` each add one call at their own existing
audit point, carrying `status`/`stage_id` (and, for stage, the pipeline
stage's *name*, since a human names a stage by name, not by UUID).
`TaskService` opts into the identical generic hook (`_workflow_entity_type`)
despite carrying no tenant-defined fields — the two capabilities are
independent, and `WorkflowEntityType` is a strict superset of
`CrmEntityType` for exactly this reason.

**The engine (`BE/workflows/*`).** `WorkflowRuleService` is CRUD plus
configuration-time validation — a `FIELD_CHANGED` trigger must name a real
column (checked via `class_mapper` against the entity's own model), an
action must apply to the entity it is attached to (`CHANGE_STAGE` only on
`OPPORTUNITY`, `CHANGE_STATUS` only on `LEAD`, `CREATE_TASK`/`CREATE_ACTIVITY`/
`CREATE_NOTE` never on a `TASK`-triggered rule since a task cannot be a
polymorphic link's target), `UPDATE_FIELD` may only reach a field each
entity's own PATCH schema already exposes — the same allow-list that keeps a
blueprint-guarded column (`status`, `stage_id`) reachable only through
`CHANGE_STATUS`/`CHANGE_STAGE`, never as a bypass. A rule is always created
inactive, like a blueprint.

`workflows.conditions.rule_matches_trigger` is a pure function (no session,
no I/O) deciding whether an event's `trigger` reason and `changed_fields`
delta satisfy a rule's `trigger_type`/`trigger_config` — unit-tested
exhaustively, including the numeric-formatting bug described below.
`workflows.conditions.matches_conditions` is a thin wrapper over
`layouts.evaluate.evaluate_condition`/`evaluate_rule` — the *same* operator
vocabulary a Checkpoint 4 conditional-field rule already evaluates records
against, not a second implementation to keep in step with the first. A new
public `TenantScopedService.workflow_context()` builds the record's current
field values (built-in columns + flattened custom fields) for condition
evaluation — the same re-read-fresh-from-the-database discipline the outbox's
own module docstring states, so a condition never evaluates against a value
that went stale between enqueue and delivery.

`workflows.actions.execute_action` is the action dispatcher, and its module
docstring states the rule this checkpoint's brief demanded explicitly:
**every action calls the entity's own service** — `LeadService.change_status`,
`OpportunityService.change_stage`, `TaskService.create_task`,
`EmailService.create_message`, `NotificationService.notify` — never a second,
automation-only write path. `actor_id=None`/`principal=None` throughout,
the same "internal caller with no request behind it" shape
`change_status`/`change_stage` already documented for a background job
before this checkpoint existed. Concretely: tenant isolation, RLS,
required-field checks and the built-in state machine all still apply to a
workflow's own writes; a blueprint transition's `required_permission` does
**not** apply (there is no user to hold it) — pre-existing, documented
`BlueprintGuard` behaviour, not a gap this checkpoint introduced or could
close without changing what a background job has always meant in this
codebase.

**Execution, idempotency and loop protection (`workflows.service._run_rule`).**
Shared by both the outbox handler and the scheduled scan. A `WorkflowRun`
row is inserted *before* any action runs, inside its own SAVEPOINT
(`session.begin_nested()`), carrying a unique `(workflow_rule_id,
source_event_id)` — or, for a scheduled rule with no triggering event,
`(workflow_rule_id, dedupe_key)` where the key embeds the day
(`f"{rule_id}:{record_id}:{date}"`). A second attempt at the same event (the
outbox's own at-least-once redelivery, documented in `platform.events.service`
as an expected failure mode, not a bug) or the same scheduled day hits
`IntegrityError` inside that savepoint and is treated as "already handled" —
proven by a test that calls the same handler twice on the same event and
asserts exactly one task exists afterward. Each of a rule's actions then runs
inside its *own* savepoint, so one action's failure (a rejected email, a
blueprint refusal) rolls back only that action's partial writes; the
`WorkflowRun` row and every action before and after it are unaffected — a
run's `status` is `SUCCEEDED`/`PARTIAL`/`FAILED` accordingly, with a
per-action `action_results` entry recording what happened.

Loop protection is a depth counter carried in a `ContextVar`
(`workflows.context`), not a lock or a per-rule flag — a lock would
serialize unrelated workflows, a per-rule flag would not stop *different*
rules chaining into each other. Every `crm.record.event_occurred` payload
carries a `correlation_id` and `depth`, decided at *enqueue* time: fresh
(depth 0) for a human-initiated write, or inherited-and-incremented when the
write is itself a workflow action's consequence (the engine sets the context
variable only while running a rule's actions). Once depth would exceed
`MAX_WORKFLOW_CHAIN_DEPTH` (5), the *next* event in the chain is not enqueued
at all — the write itself always succeeds; only further automation stops.
Proven with two workflows configured to retrigger each other indefinitely
(`A: field X → set field Y`, `B: field Y → set field X`): draining the
outbox 20 times produces a bounded, small number of total runs, never 20.

**Scheduled automation (`workflows.service.scan_scheduled_workflows`).** A
periodic ARQ cron job (every 15 minutes — `SCHEDULED`/`TASK_DUE` rules
dedupe by day, so faster polling buys nothing) evaluates rules with no
triggering event: `SCHEDULED` watches an entity's own date column (currently
`Opportunity.expected_close_date` — a per-entity allow-list,
`conditions.SCHEDULED_DATE_FIELDS`, the same closed-vocabulary discipline
`BlueprintField` uses, extensible by adding an entry rather than opening it
up); `TASK_DUE` watches `Task.due_date` directly. Both use a single signed
`offset_minutes`: zero fires as the date passes, negative fires that many
minutes *before* it ("3 days before close date" = `-4320`). Because
`app/worker.py` must not import `app.products` (`pyproject.toml`'s `TID251`
has no exemption for it, unlike the composition root), the scan is reached
through a small registry `worker.py` itself owns
(`register_scheduled_workflow_scanner`) — the composition root
(`app/api/router.py`) registers the real implementation from the same
function that already registers every outbox handler, so the worker process
picks it up via the identical `register_event_handlers()` call it was
already making at ARQ startup.

**Blueprint integration — reused, not extended.** No change to
`BE/blueprints/*` at all. `CHANGE_STAGE`/`CHANGE_STATUS` actions call
`OpportunityService.change_stage`/`LeadService.change_status` directly, so
an active blueprint refuses a workflow's attempted move exactly as it would
refuse a person's — proven in the browser (see below) and in an integration
test that configures a blueprint allowing `Negotiation → Closed Won` only,
points a workflow's `CHANGE_STAGE` action at `Closed Won` from
`Qualification`, and asserts the run is recorded `FAILED` with the deal
never having moved.

**Notifications — one new kind, no migration.** `SEND_NOTIFICATION` calls
`platform.notifications.NotificationService.notify` directly with kind
`WORKFLOW_ALERT`. No schema change: `Notification.kind` is a plain `String`
column by design (stated in `NotificationKind`'s own docstring — "a new kind
must not require an `ALTER TYPE`"), and `notify()` itself takes `kind: str`.
The existing bell/unread-count/mark-read UI needed no changes to display it.

**Email — reused, not re-plumbed.** `SEND_EMAIL` calls
`EmailService.create_message(..., values={"send": True})` — the same
enqueue-on-commit path a person's own Send button uses — either against a
saved `EmailTemplate` (via `EmailService.render_template`, which already
resolves `{{record.<field>}}`/`{{sender.*}}`/`{{organization.*}}` variables
and leaves an unknown placeholder untouched rather than guessing) or a
static subject/body run through the same `resolve_variables`/
`render_placeholders` pair directly. No new templating mechanism, no
arbitrary template execution — the same allow-listed variable vocabulary
`emails/variables.py` already exposes per entity type.

**A permission module, seeded exactly like blueprints.** `workflows`
(`VIEW`/`VIEW_TEAM`/`VIEW_ALL`/`CREATE`/`EDIT`/`DELETE`/`EXPORT`/`ADMIN`) —
`VIEW` granted to every system role (a rep whose record a workflow touched
has to be able to see which rule did it, in the execution history),
everything else Admin-only, identical reasoning to `blueprints`. Seeded by
migration `20260918_0100`, the same `INSERT ... ON CONFLICT DO NOTHING`
pattern `20260912_0100_blueprints.py` established.

### Three real bugs found and fixed via testing, not assumed away

1. **Module boundary violation.** `workflows.service.scan_scheduled_workflows`
   initially queried `platform.organizations` directly
   (`from app.platform.organizations.models import Organization,
   OrganizationStatus`) — copied from the notifications module's own
   cross-organization scan without noticing that caller is *inside*
   Platform (allowed to reach its own models) while `workflows` is a
   product (not allowed to reach Platform internals,
   `ARCHITECTURE-BOUNDARIES.md` rule 2). Caught by the existing automated
   boundary test (`test_module_boundaries.py`), not by inspection. Fixed by
   adding `OrganizationService.list_active_organization_ids()` — a one-line
   seam mirroring `member_directory`'s own reasoning — and calling that
   instead.
2. **A numeric `FIELD_CHANGED` trigger could silently never fire.** Found in
   live browser verification, not by a test — a rule watching
   `Opportunity.deal_value` changing to `"75000.00"` never matched a real
   change to $75,000, because `jsonable_encoder` re-serializes a
   whole-number `Decimal` without its trailing zeros (`Decimal("75000.00")`
   → JSON `75000`), and the trigger-matching code compared the two as plain
   text. Fixed by making `workflows.conditions._as_text` numeric-first
   (parse both sides as a float and compare when possible, falling back to
   case-insensitive text for anything that is not a number — mirroring, for
   this one comparison, the same "one operator works for every field type"
   reasoning `layouts.evaluate` already states for its own operators).
   Regression-tested at both the unit level (`test_workflow_conditions.py`)
   and the integration level (`test_workflows.py`, an opportunity's
   `deal_value` actually changing through the real API and outbox).
3. **`CREATE_NOTE` was completely non-functional.** `workflows.actions._create_note`
   built its `values` dict with the key `"body"`; the `Note` model's actual
   column is `content` (`NoteCreate`/`NoteUpdate` agree). Every `CREATE_NOTE`
   action would have raised inside its own per-action savepoint, been caught,
   and recorded as a `FAILED` action — never crashing a run, but never
   creating a note either, silently, since nothing had yet exercised this
   action type. Found only once deliberate integration-test coverage was
   added for every action type this checkpoint claims to support, not merely
   the ones already exercised by other scenarios — the reason that pass
   (Step 17: "meaningful tests… field updates, task creation, notification
   creation, email action, owner assignment") is worth taking literally
   rather than treating as satisfied by partial coverage. Fixed by mapping
   the action's own `body` config key to the model's `content` column;
   `test_record_created_adds_a_note` now asserts the real, resolved note
   content through `GET /crm/notes`. The same coverage pass added
   `test_record_created_logs_an_activity` (`CREATE_ACTIVITY`),
   `test_record_created_assigns_a_different_owner` (`ASSIGN_OWNER`) and
   `test_record_created_sends_an_email` (`SEND_EMAIL`, asserting a real
   `EmailMessage` was queued with the resolved subject) — all passed on
   first run once written correctly, and all also caught two *test*
   authoring bugs along the way: two earlier assertions checked only that a
   task title/notification title contained a static substring
   ("Follow up with"/"New lead"), which an *unresolved* `{{record.name}}`
   placeholder would also have satisfied (`LEAD` offers `record.full_name`,
   not `record.name` — the exact mistake the browser-verification section
   below describes making live). Both tightened to assert the fully
   resolved text.

### APIs

`/api/v1/crm/workflows` — `GET`/`POST` (list/create), `GET`/`PATCH`/`DELETE
/{id}` (detail/update-or-activate/archive), `POST /{id}/duplicate`
(deactivated copy, uniquely named), `GET /{id}/runs` (paginated execution
history for one rule), `GET /runs/all` (paginated history across every
rule — the admin activity feed). All gated on the `workflows` permission
module (`require_permission`), all tenant-scoped through the same
`get_or_404` every other CRM resource uses.

### DB migrations

`20260918_0100_workflow_automation.py` — `crm.workflow_rules` (configuration,
soft-deleted, RLS-forced) and `crm.workflow_runs` (append-only history,
RLS-forced, no soft-delete — an execution record that could be edited after
the fact would not be a record); three new native enums
(`workflow_entity_type`, `workflow_trigger_type`, `workflow_run_status`);
the two idempotency-carrying partial unique indexes described above; the
`workflows` permission module seeded and granted. Verified from zero — every
migration in the project, including this one, applied cleanly in order on a
freshly created database — and its `downgrade()`/re-`upgrade()` round-trip
was exercised directly, not merely written.

### Workers / background jobs

`app/worker.py` gained one function, `run_scheduled_workflows`, and one cron
entry (`minute={0, 15, 30, 45}`), alongside the pre-existing `drain_outbox`
(now also the delivery path for `crm.record.event_occurred`) and
`dispatch_reminders`. No new process: the same ARQ worker started by
`uv run arq app.worker.WorkerSettings`.

### Security validation

- **Tenant isolation:** both new tables are RLS-forced under the same
  `crm` schema policy as every other CRM table; verified directly against
  the database (`\d crm.workflow_rules`/`crm.workflow_runs` show the forced
  policy) after a from-zero migration, not merely asserted from the model
  definition.
- **RBAC:** `workflows.VIEW`/`CREATE`/`EDIT`/`DELETE` enforced exactly like
  blueprints — a rep can read the configured rules and their run history
  but cannot create, edit or delete one (integration-tested); another
  tenant's workflow is a 404, never a 403 (does not confirm existence).
- **RecordVisibility / execution identity:** a workflow action's write goes
  through the triggering record's own tenant-scoped session (the outbox
  dispatcher applies `apply_tenant_context` from the event's own
  `organization_id` column — never the payload — before the handler runs),
  so a workflow cannot read or write across the tenant boundary any more
  than the outbox itself already prevents. Execution identity is
  `actor_id=None`/`principal=None` throughout — documented above, and
  identical to the pre-existing shape a background job or data fix already
  used for `change_status`/`change_stage`.
- **Blueprint integrity preserved:** a workflow cannot bypass a blueprint's
  guarded transition — proven, not merely argued, in both an integration
  test and live browser verification (see below).
- **No automation-only write path exists anywhere in `workflows.actions`** —
  every action is a call into an existing, already-validated service method.

### Tests

- **New:** `tests/unit/test_workflow_conditions.py` — **15 tests**, pure
  trigger-matching and condition-evaluation logic, no database — every
  `WorkflowTriggerType` exercised including negative cases, plus the
  numeric-formatting regression test. `tests/integration/test_workflows.py`
  — **26 tests**, real PostgreSQL and the real `EventDispatcher`, matching
  `test_outbox.py`'s own standard: CRUD/validation/permissions/tenant
  isolation; one end-to-end scenario per action type this checkpoint claims
  to support (`SEND_NOTIFICATION`, `UPDATE_FIELD`, `CREATE_TASK`,
  `CREATE_NOTE`, `CREATE_ACTIVITY`, `ASSIGN_OWNER`, `SEND_EMAIL`,
  `CHANGE_STAGE`), each driven through the real API and drained through the
  real outbox, each asserting the *resolved* effect (a real note's content,
  a real task's title with its placeholder substituted, a real queued
  `EmailMessage`'s subject) rather than a loose substring; a numeric
  field-changed trigger; a disabled workflow provably not firing and an
  activated one provably firing; a blueprint-guarded `CHANGE_STAGE` action
  failing correctly without corrupting the record; idempotency against a
  simulated redelivery of the same event; loop protection against two
  mutually retriggering workflows; and both scheduled-trigger shapes,
  `SCHEDULED`/`TASK_DUE`, including the once-per-day dedupe. **41 tests
  total, all green.**
- **Modified:** `tests/integration/conftest.py` gained two cleanup
  statements (`crm.workflow_runs`, `crm.workflow_rules`) in the tenant-scoped
  autouse fixture — both are RLS-forced tables the existing unscoped cleanup
  cannot reach, the same reason every other tenant-scoped table is listed
  there.
- **Targeted regression, run against a dedicated, freshly migrated database
  separate from the one used for live browser verification** (to avoid the
  autouse cleanup fixture wiping manually created browser-test data
  mid-session — never two pytest runs, or a pytest run and a live server,
  sharing one database at once): `test_workflows.py` + `test_workflow_conditions.py`
  (41 tests, including the reliability suite and the per-action-type
  coverage above), `test_blueprints.py`, `test_crm_workflows.py`,
  `test_outbox.py`, `test_notifications.py`, `test_account_relationships.py`,
  `test_calendar.py`, `test_rbac.py` and `test_tenant_isolation.py` all
  green — no regression from the generic create/update hook added to
  `shared/service.py`, from `LeadService`/`OpportunityService`'s new
  enqueue calls, or from `TaskService` opting into the same hook.
- **One full backend regression run** (`uv run pytest`, no path filter — a
  third dedicated, freshly migrated database, per Step 17's "run ONE clean
  full backend regression suite"): **1950 collected — 2 failed, both
  pre-existing and unrelated (below); the rest passed or skipped**
  (environment-dependent skips, e.g. tests requiring a live external
  provider key this local run does not have — consistent with every prior
  checkpoint's own regression notes). The run's own final summary line was
  lost to an output-capture artifact of the terminal this session ran in
  (the "short test summary info" block naming both failures by test id was
  captured intact and is exact; the aggregate pass/skip counts above are
  derived by summing progress-line markers against a `--collect-only` total
  of 1950, not copied from a summary line this session did not actually
  see — stated as derived rather than presented as a false-precision quote).
- **Static analysis:** `ruff check app tests migrations` clean; `mypy app`
  (strict mode, matching CI) clean across all 325 backend source files;
  frontend `tsc --noEmit` clean; frontend `eslint .` clean (two unused-import
  warnings caught and fixed during development); frontend `next build`
  succeeds, `/admin/workflows` present in the route manifest.

### Pre-existing, unrelated test failures (isolated, not silently ignored)

Both confirmed via `git diff d7704ad -- <file>` returning empty — neither
file differs from the Checkpoint 5 completion point this checkpoint started
from, so neither failure can be this checkpoint's own regression:

- `tests/unit/test_application.py::test_production_settings_disable_docs`
  fails with a `pydantic` validation error (`STORAGE_BUCKET`/
  `STORAGE_ACCESS_KEY_ID`/`STORAGE_SECRET_ACCESS_KEY` required when
  `ENVIRONMENT=production`). A storage-required-in-production validator was
  evidently added to `Settings` at some point without updating this one
  test's fixture. Reproduces every time, in isolation or in the full suite.
- `tests/unit/test_ai_connection.py::test_no_trace_of_the_key_in_redis_logs_or_results`
  failed only inside the full-suite run (`assert any(entry["event"] ==
  "ai_connection_checked" for entry in logs)` found no matching entry, even
  though the identical log line is visible in the test's own captured
  stdout) and passed cleanly when re-run in isolation immediately after —
  a genuinely flaky, state-dependent test (most likely a `structlog`
  log-capture/context interaction with whatever ran immediately before it
  in the full suite's collection order), not a deterministic failure.

Neither is fixed here: one is a production-settings validator gap, the
other a pre-existing flake in an unrelated AI-connection test file — both
outside a workflow-automation checkpoint's scope, and both would have been
silently invisible if this section simply reported "backend suite passed."

### Browser verification (Step 18)

Real backend (`uvicorn`, real PostgreSQL/Redis), real ARQ worker
(`uv run arq app.worker.WorkerSettings`), a throwaway signup/organization
created through the actual `/signup` flow (not seeded via SQL). Verified
live, end to end:

1. **Create → configure → activate → fire → verify → inspect history**, on
   `/admin/workflows`: a `RECORD_CREATED` rule (Lead, `SEND_NOTIFICATION`)
   created inactive, confirmed inert while inactive (creating a matching
   lead produced no notification), activated with the same confirm-dialog
   pattern blueprints use, then fired for real on the next lead created —
   the notification appeared in the real bell, and the run appeared in
   `GET /{id}/runs` as `SUCCEEDED`.
2. **A `STATUS_CHANGED` trigger with a condition, `CREATE_TASK` action, and
   `{{record.full_name}}` variable substitution**: moved a real lead
   `NEW → CONTACTED → QUALIFIED` through the actual status-transition
   endpoint; a real task ("Follow up with Margaret Hamilton") appeared on
   `/tasks`, correctly linked to the lead. (An earlier attempt using
   `{{record.name}}` — a placeholder that does not exist for `LEAD`, which
   exposes `full_name` instead — correctly left the placeholder
   unresolved rather than silently guessing; this surfaced a real UI
   hint-text bug, `recordNamePlaceholder()`, fixed and re-verified.)
3. **A `FIELD_CHANGED` trigger on a numeric field (`deal_value`) with a
   `CHANGE_STAGE` action, guarded by an active blueprint** that permits
   only `Negotiation → Closed Won`: changing an opportunity's deal value
   while it sat in `Qualification` correctly left the opportunity in
   `Qualification` (the blueprint refused the jump) and the run history
   showed `FAILED`, "1 action(s) failed" — proof, in the browser, that a
   workflow's action carries no more authority than a person's own click.
   This scenario is also what surfaced the numeric-formatting bug above:
   the *first* attempt did not fire at all (wrong reason: config mismatch,
   not the blueprint), which is exactly why "the rule didn't run" and "the
   rule ran and was correctly refused" were checked as two separate,
   distinguishable outcomes rather than assumed from one one passing test.
4. Confirmed dynamic, entity-scoped trigger/action option lists in the
   admin UI (an `Opportunity` workflow offers `Stage changes`/`A date field
   arrives`; a `Lead` workflow offers `Status changes`; `CHANGE_STAGE` only
   appears as an available action for an `Opportunity`-scoped rule).

### Known limitations

- **No outbound webhook action.** Named in the checkpoint brief's action
  list; not built. Every other listed action (field update, assign owner,
  create task, create activity, create follow-up, send email, send
  notification, change stage/status, add note) is implemented.
- **"No activity in N days" idle-record detection was not built.** The
  brief's Step 11 names it as an example scheduled trigger; there is no
  existing "last activity at" column on any entity to scan (activities are
  a separate, unrelated table with no rollup onto the record they describe),
  and adding one is a schema change beyond a workflow-engine checkpoint's
  scope. `SCHEDULED`/`TASK_DUE` (date-field-reached, task-overdue) are
  built and tested.
- **`SCHEDULED` supports one entity/field today:** `Opportunity.expected_close_date`.
  The allow-list (`conditions.SCHEDULED_DATE_FIELDS`) is deliberately closed,
  like `BlueprintField` — extending it to another entity's date column is
  one dictionary entry, not a redesign, and was left at one proven case
  rather than speculatively widened.
- **A `FIELD_CHANGED` trigger's watched field is free text, validated
  server-side against the entity's real columns but not offered as a
  picker in the admin UI** (unlike, say, `UPDATE_FIELD`'s target field,
  which *is* a populated `<select>`). Consistent with blueprints'
  `required_fields`, which is the same free-text-validated-server-side
  shape for the identical reason — the built-in column set differs per
  entity and a full per-field picker was judged more surface than this
  checkpoint's scope, not an oversight.
- **A workflow's `UPDATE_FIELD`/condition targets built-in columns only** —
  a tenant's custom field cannot yet be named as an `UPDATE_FIELD` target
  or a `FIELD_CHANGED` trigger's watched field (it *can* be read in a
  condition's `field_key`, since `workflow_context()` flattens custom
  fields into the same namespace). The same category of gap Checkpoint 5's
  report builder documented for its own select/group targets.
- **`Notifications` (#59) stays partial** for reasons unrelated to this
  checkpoint: no user notification preferences, no push delivery — this
  checkpoint added a new *kind* (`WORKFLOW_ALERT`) to an unchanged delivery
  mechanism.
- Nothing above was faked or assumed to pass; each is a stated design
  boundary or a scope line this checkpoint chose not to cross.

### Environment / verification notes

- Docker (`s3k-postgres` on port 5434, `s3k-minio`, `s3k-redis`) was already
  running. Two throwaway databases were created for this checkpoint and
  kept strictly separate for their whole lifetime: one for live browser
  verification (seeded through the real signup flow, never touched by an
  autouse test-cleanup fixture that deletes all organizations), one for
  automated `pytest` runs (migrated from zero, wiped and reseeded by the
  test suite's own fixtures on every run). This separation is deliberate
  and was maintained throughout — the note above about a Checkpoint 5
  session accidentally running two pytest processes against one database
  was read and specifically designed around, not repeated.
- Restarting the local `uvicorn` dev server (picking up a mid-session code
  fix) invalidates every session's access token: in development, with no
  `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` configured, tokens are signed with a
  process-local ephemeral key that does not survive a restart (by design —
  documented in `backend/.env.example`). Re-authenticating after such a
  restart is expected, not a bug; encountered and worked around twice
  during this session's verification (once after fixing the module-boundary
  violation, once after fixing the numeric-comparison bug), each time by
  signing back in and re-driving the affected scenario to a real, freshly
  observed pass rather than assuming the fix worked from the code change
  alone.
- The ARQ worker process does not hot-reload on code changes (unlike the
  `uvicorn --reload` API process); it was restarted by hand after each
  backend fix that touched code the worker actually executes
  (`workflows/service.py`, `workflows/conditions.py`), confirmed via its
  own startup log line before re-running the affected browser scenario.

## Checkpoint 7 — Completed (2026-09-19)

AI Account Summary, Account Intelligence, Next-Best-Action, AI email
drafting, meeting-to-CRM extraction, a natural-language question box and
rule-based prioritization — items 4–8 and 10, plus item 9 moved from missing
to partial (read-only NL, not NL commands). Started by a prior session (which
left the backend module, minus its router/migration/tests, stashed rather
than committed) and finished here: this session recovered that work,
completed the remaining backend surface, fixed two real bugs found while
testing it, and built the frontend.

### Files changed

Backend:
- `backend/app/products/crm/ai_insights/{__init__,models,repository,context,
  structured,prompts,schemas,service,prioritization,insights}.py` — the
  module the prior session left stashed. `models.py`: `crm.ai_generations`
  (append-only, one row per feature call, `AiFeature`/`AiGenerationStatus`/
  `AiFeedbackRating` enums, not owner-scoped — anyone who can see the record
  can see its AI history, like Notes). `context.py`: permission-filtered CRM
  context for an account/opportunity/lead, extending the pattern
  `market_insights/context.py` established. `structured.py`: `run_structured`
  — the one path every non-research feature uses to get a
  Pydantic-validated answer, `web_search=False`, a fenced-JSON tolerant
  parser, a typed `ai_invalid_output` 502 on failure. `prompts.py`:
  `build_prompt` — task instructions first, a "treat CRM/user text as data"
  standing-rules block last, `<crm-data>`/`<user-text>` delimiters, the
  output shape generated from the *real* Pydantic schema
  (`model_json_schema()`) rather than a hand-written, driftable hint.
  `prioritization.py`/`insights.py`: pure, unit-tested rule-based scoring and
  triage queries — no model call, so "rules first, AI explanation second"
  is actually true rather than merely claimed. `service.py`: the public
  `AiInsightsService` tying it together — resolve the record through its own
  `get_or_404(..., visibility=...)`, build context, call the gateway,
  validate, persist.
- `backend/app/products/crm/ai_insights/router.py` (new this session) — every
  endpoint under `/crm/ai-insights`; `ai_insights.VIEW` for a cached read,
  `.CREATE` for a fresh model call, `.EDIT` for feedback and applying a
  meeting extraction's items.
- `backend/migrations/versions/20260919_0100_ai_insights.py` (new this
  session) — `crm.ai_generations` + its three enums, seeds `ai_insights.*`
  permissions and grants them to Admin (full)/Manager (`VIEW`, `VIEW_ALL`,
  `CREATE`, `EDIT`, `DELETE`, `EXPORT`)/User (`VIEW`, `CREATE`, `EDIT`) —
  mirrors `catalog._MANAGER_ACTIONS`/`_USER_ACTIONS` for the module the
  stashed `catalog.py` edit had already registered. Verified against a
  from-zero database (`alembic upgrade head` from empty), not only the dev
  database.
- `backend/app/api/router.py` — registers the router at `/crm/ai-insights`.
- **Two real bugs found and fixed while testing, not in the original
  stash:**
  1. `apply_meeting_actions` called `TaskService.create_task`/
     `NoteService.create_note`/`OpportunityService.update_open` directly.
     Those are plain CRUD methods with no permission check of their own — in
     this codebase that check is the router's `require_permission`
     dependency, which nothing between the meeting-apply endpoint and those
     calls provided. A caller holding only `ai_insights.CREATE` could create
     tasks/notes or edit a deal's value through meeting extraction regardless
     of their `tasks`/`notes`/`opportunities` permissions. Fixed by checking
     the same permission each entity's own create/edit endpoint requires
     before each item is applied, reported as `FAILED` (not raised) so the
     other selected items still apply.
  2. `apply_meeting_actions` re-validated the generation's stored `content`
     against `MeetingExtractionOutput` (`extra="forbid"`) on every call —
     including the *second* call, after the first had already written
     `applied_indexes` into that same JSONB column. A second apply (the
     "already applied" idempotency path §16 asks for) failed validation
     instead of returning `SKIPPED`. Fixed by excluding that bookkeeping key
     before validating.
  3. Also added `lead_id` to `EmailDraftRequest`/`draft_email` (the stashed
     version only supported contact/account/opportunity) and `entity_label`
     to `PriorityScoreResponse` (the priority queue had no record name to
     show without a second fetch per row) — both small, mechanical additions
     in the same shape as what was already there, not scope additions.

Frontend (none of it existed before this session — the AI pages were
`AiFeaturePending` placeholders and `AIMeetingAssistant.tsx`/
`AICommandBar.tsx`/`components/crm/ai/nba/*` were orphans over fixture data):
- `frontend/features/ai/ai-insights.ts` (new) — the one client for every
  `/crm/ai-insights` endpoint, mirroring `market_insights/index.ts`'s shape.
- `frontend/components/crm/ai/AiRecordPanel.tsx` (new) — the "AI" tab/section
  on Account/Deal/Lead 360: a cached summary (Refresh writes a new row,
  never overwrites — the UI reads `GET` on mount, only `POST` on Generate),
  Account Intelligence (accounts only), Next Best Action (deals/leads only),
  thumbs up/down feedback, and a "Meeting notes → CRM" card (accounts/deals)
  — paste notes, Extract, review each proposed item, Apply only what's
  checked; nothing is written until Apply.
- `frontend/app/(crm)/ai/insights/page.tsx` — rebuilt from the placeholder
  into the real Insights Digest (deals at risk, stale opportunities,
  neglected leads, quiet accounts, overdue tasks — all rule-based, render
  with no AI connection) plus a natural-language question box (needs AI;
  translates to the existing report engine, never raw SQL).
- `frontend/app/(crm)/ai/next-best-action/page.tsx` — rebuilt into the real
  priority queue for open deals and leads (`GET /priority/*`, rule-based, no
  AI needed to rank) with an "Explain" action per row that narrates the
  already-computed score.
- `frontend/components/crm/emails/ComposeEmailDrawer.tsx` — a "Draft with
  AI" panel (tone + free-text instruction) that fills the subject/body for
  review; never sends automatically.
- `frontend/app/(crm)/{accounts,opportunities,leads}/[id]/page.tsx` — mount
  `AiRecordPanel`.

**Left deliberately unchanged, not overlooked:** the pre-existing mock
components (`AIMeetingAssistant.tsx`, `AICommandBar.tsx`,
`components/crm/ai/nba/*`, `AiInsightsReport.tsx` and siblings under
`components/crm/ai/insights/`) were not wired to real data or deleted — real,
simpler components were built instead, matching what the backend actually
returns rather than the richer shape the old fixtures implied. Removing the
now-fully-orphaned files is a follow-up, not attempted here to keep this
checkpoint's diff to what it added.

### Known limitations

- **Natural-language *commands* are not built** (#9 stays partial): the
  question box translates to a report and runs it — read-only, through the
  existing permission-checked report engine. "Mark this lead qualified" from
  plain language is out of scope, per the module's own docstring (never
  executes a write itself).
- **Priority score (#10) is not shown on the Accounts/Opportunities/Leads
  list or Kanban views** — only on the dedicated Next Best Action queue page
  and, per record, the AI panel.
- **Meeting extraction only accepts an account or a deal as context**
  (`account_id`/`opportunity_id`), not a lead or a contact — matches what
  `context.py` had built for Checkpoint 7's other features; extending it to
  leads is a small addition, not attempted here to stay within scope.
- No new E2E (Playwright) coverage was added for these screens — see
  Checkpoint 8.

### Tests

- New: `tests/unit/test_ai_insights_prioritization.py` (14),
  `tests/unit/test_ai_insights_structured.py` (10),
  `tests/unit/test_ai_insights_prompts.py` (12) — pure functions, no
  database: scoring rules, JSON extraction/validation, and prompt-injection
  defense (CRM data and user-authored text delimited and labelled, standing
  rules ordered after the task, the schema hint generated from the real
  Pydantic model). `tests/integration/test_ai_insights.py` (19) — against
  real PostgreSQL and real RBAC, only the model call stubbed: generate/cache/
  refresh/history for a summary, the full `AccountIntelligenceOutput` shape,
  a malformed model answer surfacing as `502 ai_invalid_output` not a 500,
  Next Best Action, the email-draft validator, meeting extraction writing
  nothing until applied, applying creates the confirmed task/note/deal-value
  update, re-applying the same index is `SKIPPED` not duplicated (the bug
  fix above, specifically exercised), NL query understood/not-understood,
  the priority queue and its "explain" action (including 404 on a closed
  deal), feedback, and cross-tenant 404 isolation.
- Full backend suite (`uv run pytest`, every unit and integration test, the
  55 new ones included): **26 failed, the rest passed.** All 26 pre-date this
  checkpoint and are environmental, not a regression it introduced — verified
  by file: **25 in `tests/integration/test_attachments.py`**, every one the
  same `InvalidAccessKeyId` from MinIO (this worktree's `backend/.env` was
  created fresh this session from `.env.example`'s placeholder storage
  credentials, which do not match this machine's actual MinIO container —
  exactly the "no root `.env` means random MinIO keys" failure mode already
  on record, unrelated to `ai_insights`); **1 in
  `tests/unit/test_ai_connection.py::test_no_trace_of_the_key_in_redis_logs_or_results`**,
  a structlog `capture_logs()` timing assertion unrelated to any file this
  checkpoint touched. Zero failures in any `ai_insights`/`ai-insights` test,
  and zero in any file this checkpoint modified outside `ai_insights/*`.

### Static analysis

- **Ruff** (`uv run ruff check app migrations`): clean.
- **mypy** (`uv run mypy app`): clean, 336 source files.
- **Frontend `tsc --noEmit`**: clean (after `npm install`, which had never
  been run in this worktree — `node_modules` did not exist).
- **Frontend `eslint .`**: clean (fixed 5 `react-hooks/set-state-in-effect`
  errors — a synchronous `setState` at the top of an effect body — by
  matching the codebase's own `useRecord.ts` pattern: derive "loading" from
  whether a keyed result has arrived yet, rather than a separate flag set
  synchronously).
- **Frontend `next build`**: succeeds; all 57 routes generate, including
  every `/ai*` page and the three record-detail pages with the new AI panel.

### Verified in a running browser, not only statically

Signed up a fresh organization against a throwaway database
(`s3k_crm_ck7_dev`, separate from the `pytest` database the whole time — the
two were never touched by the same process), created a real account and a
$5,000,000 deal, and confirmed: the Account 360 "AI" tab renders and its
`GET` endpoints correctly return "no summary yet" rather than erroring; the
Next Best Action queue shows the real deal by name (`entity_label`), scored
from its real fields with named reasons ("Large deal", "No recorded
activity"); the Insights Digest renders its five categories with no AI
provider configured (proving the "works without AI" design point, not just
asserting it); "Explain" and the meeting-extraction "Extract" action both
surface a clean, typed "AI is not connected" message rather than a crash
when attempted without a provider key (this dev environment has none — per
the project's standing rule, that is never faked); "Draft with AI" renders
in the compose drawer. No console errors traced to this checkpoint's code.

### Environment / verification notes

- Same throwaway-database discipline as Checkpoint 6: one database for the
  automated suite (migrated from zero, first proving `20260919_0100` applies
  cleanly on top of `20260918_0100`), a separate one for live browser
  verification, never run against by the same process at once.
- This worktree's own `.claude/launch.json`-driven preview tooling would not
  start any server, always refusing on an unrelated process already holding
  port 3000 (a different local project entirely, confirmed by navigating to
  it) regardless of which named configuration was requested or that
  configuration's own port. Worked around by starting `uvicorn`/`next dev`
  directly and pointing the browser at the resulting port; not a code issue
  in this checkpoint.
- `npm install` had never been run in this worktree (`frontend/node_modules`
  did not exist), which is why `tsc`/`eslint`/`next build` could not run
  before this session ran it.

## Next Exact Step

**Checkpoint 8 — Security + performance + complete regression/E2E testing +
documentation** (audit items 67, 71, 72, 75, plus the full suite). Per
"Recommended Implementation Order," this is the hardening pass: custom role
create/edit (`POST /roles`), an MFA/SSO decision, load/performance tests
beyond the existing search benchmark, Playwright E2E coverage for every
checkpoint that shipped without it (AI, import, merge, dashboards builder,
reports detail, Account 360 — now including the Checkpoint 7 AI screens),
and a documentation pass. Custom modules (40) remain explicitly out of scope
for this plan (see the note above the Checkpoints table).
