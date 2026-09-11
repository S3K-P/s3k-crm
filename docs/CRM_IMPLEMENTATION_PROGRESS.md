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

**75 features audited: 43 ✅ COMPLETE · 20 🟡 PARTIAL · 12 🔴 MISSING** (Checkpoint 2 moved primary contacts to complete and Kanban drag-and-drop from missing to partial; Checkpoint 3 wired the Leads board to move Kanban drag-and-drop to complete, and substantially extended Activities, Tasks, Timeline, Files and Email without changing their own status; Checkpoint 4 built the form/layout builder, conditional fields, inline and bulk editing, moving items 31–36, 47 and 48 to complete and 41 from missing to partial; see the Checkpoints table below for what each checkpoint changed).

- **The CRM core is solid.** Accounts, contacts, leads, deals, pipeline,
  activities, tasks, meetings, notes, attachments, email, search, saved views,
  import/export, custom fields, blueprints, RBAC, record-level visibility,
  row-level-security tenant isolation and audit logging are implemented end to
  end. Each has a backend module, a migration, a real frontend screen, and
  integration tests.
- **AI is the largest gap.** The AI gateway (`backend/app/platform/ai/`,
  ADR-016) is real and works with Anthropic or Gemini. Exactly one product
  feature uses it: **Market Insights** (company research, with
  permission-filtered CRM context). AI Insights, Next-Best-Action, AI email,
  meeting-to-CRM, natural-language commands and prioritization have no backend
  at all. Their pages render a hardcoded "AI is not connected" placeholder.
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
| 1 | AI connection/integration | 🟡 | Gateway `PF/ai/` (`service.py` `AiGatewayService`, `provider.py` `AnthropicResearchProvider` + `GeminiResearchProvider`); streaming, continuations, Redis rate limit, append-only prompt versions (`platform.ai_prompt_versions`, migration `20260827_0100`). Used only by `BE/market_insights/`. | Wire AI Insights / NBA / other AI screens to real status; add a generic non-research "completion" call path for summaries/emails (the gateway is research-shaped today). | #2, #3 |
| 2 | AI provider configuration | 🟡 | Env-only, via `Settings` in `backend/app/core/config.py`: `AI_PROVIDER` (`anthropic`\|`gemini`, default `anthropic`), per-provider key, model, limits. | No admin UI: `FE/app/(crm)/ai-settings/providers/page.tsx` is a static `AiUnavailable` placeholder. No DB-stored credentials on this branch (no `credentials.py`/`registry.py`, no `ai_provider_credentials` migration). Optional: read-only provider/model display from `/ai/status`. | #3 |
| 3 | AI health/status | 🟡 | `GET /ai/status` → `{configured, model}` (`PF/ai/router.py`). Checks that a key is **present** for the selected provider. | No live check. A revoked or invalid key still reports `configured: true` until a real call fails with `ai_not_configured`. Only 1 of 12 AI screens (Market Insights) calls it. Add provider name + admin-only live probe. | — |
| 4 | AI Account Summary | 🔴 | Nothing. Closest: a Market Insights session can be linked to an account (`POST /crm/market-insights/{id}/account`). | Endpoint + prompt that summarises one account from its CRM data (reuse `BE/market_insights/context.py` permission-filtered context); panel on the Account 360 page. | #1, #12 |
| 5 | AI Account Intelligence | 🟡 | Market Insights: web research on a company with fenced, permission-filtered CRM context, history, follow-up chat, sources panel, HTML/Markdown export (`BE/market_insights/*`, `FE/app/(crm)/ai/market-insights/page.tsx`). | CRM-internal intelligence (deal health, risk, engagement) is absent. `FE/app/(crm)/ai/insights/page.tsx` is a placeholder; its fixtures `FE/features/ai/insights/mock-data.ts` must not be used. | #1, #4 |
| 6 | AI Next-Best-Action | 🔴 | UI components exist over **mock data only** (`FE/components/crm/ai/nba/*`, `FE/features/ai/next-best-action/mock-data.ts`); the page renders `AiUnavailable`. | Backend service ranking actions from real deals/activities/tasks; replace fixtures with an API. | #1, #10, #20–24 |
| 7 | AI email generation | 🔴 | Compose drawer + templates exist (`FE/components/crm/emails/ComposeEmailDrawer.tsx`, `BE/emails/`). | "Draft with AI" endpoint returning subject/body into the compose drawer (never auto-send). | #1, #27 |
| 8 | AI meeting/activity → CRM updates | 🔴 | Orphan component `FE/components/crm/ai/AIMeetingAssistant.tsx` (imported nowhere). | Notes/transcript → proposed field updates, tasks, next steps, with explicit user confirmation before any write. | #1, #20–23, #56 |
| 9 | Natural-language CRM commands | 🔴 | Orphan `FE/components/crm/ai/AICommandBar.tsx`, `ai/insights/AiQueryPanel.tsx`. Command palette does keyword search only. | NL → structured query/actions, executed through existing permission-checked endpoints. | #1, #42, #43 |
| 10 | AI deal/lead prioritization | 🔴 | Nothing (no score columns). `FE/features/ai/scoring/` is an empty barrel. | Scoring service (rules first, AI explanation second), score shown on lists and Kanban. | #1, #15, #20 |

### B. CRM Core

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 11 | Accounts | ✅ | `BE/accounts/*`; CRUD + CSV export; soft delete, `merged_into_id`; `FE/app/(crm)/accounts/*`. | — | — |
| 12 | Account 360 | 🟡 | **Checkpoint 2:** tabbed (`Overview`/`Contacts`/`Deals`/`Activities`/`Emails`/`Notes`/`Files`/`Timeline`) via `FE/components/crm/shared/Tabs.tsx`. Summary header (`FE/components/crm/accounts/AccountSummary.tsx`) reads `GET /crm/accounts/{id}/overview` (`BE/accounts/overview.py`, `service.py:overview`): open pipeline value, won revenue, contacts count, open tasks count, next meeting, owner name, primary contact — all record-visibility-scoped, no N+1. Company details now include phone (`crm.accounts.phone`, migration `20260914_0100`). **Checkpoint 3:** the Timeline tab now merges Task created/completed, sent Email and Notes into the same stream as activities, deals and contacts (see #24). | Still no dedicated open-tasks/upcoming *list* panel on the Account page — only the count. No AI summary (Checkpoint 7). | #4, #16, #21, #24 |
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
| 42 | Global search | ✅ | `GET /crm/search` (4 entities, tsvector, permission filtered in-query, migration `20260826_0100`); `FE/components/crm/topbar/CommandPalette.tsx`; `test_search_performance.py`. | — | — |
| 43 | Advanced filtering | 🟡 | Per-list filter params + typed custom-field filters (`custom_fields/filters.py`); filters persist in saved views. | No multi-condition (AND/OR, operators) filter builder UI/API. | #45 |
| 44 | Sorting | ✅ | `sort_by`/`sort_dir` on lists, custom-field sort for sortable types; `DataTable` sorting. | — | — |
| 45 | Saved views | ✅ | `BE/views/*` (private/shared, default, 404-not-403 for others' private views); `SavedViewPicker` on accounts/contacts/leads/opportunities. | — | — |
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
| 55 | Blueprints | ✅ | `BE/blueprints/*` (rules per from→to state, required fields, required permission; narrows only); `FE/app/(crm)/admin/blueprints/page.tsx`; `test_blueprints.py`, `configuration.spec.ts`. | — | — |
| 56 | Workflow engine | 🔴 | Foundation only: transactional outbox + dispatcher (`PF/events/*`, ARQ worker `backend/app/worker.py`). `ai-settings/automations` page is a placeholder. | Rule evaluator subscribed to record events. | #57, #58 |
| 57 | Workflow rules | 🔴 | — | `crm.workflow_rules` (entity, trigger: create/update/field-change/date, conditions). | #56 |
| 58 | Workflow actions | 🔴 | — | Actions: field update, create task, send email (via outbox), notify, webhook. | #56, #59 |
| 59 | Notifications | 🟡 | `PF/notifications/*`: in-app bell, unread count, mark read; kinds MEETING_REMINDER, TASK_DUE, RECORD_ASSIGNED; scheduler + email reminders. | No user preferences, no rule-driven notifications, polling not push. | #58 |
| 60 | Follow-up automation | 🔴 | Only due-date reminders for existing tasks/meetings. | "No activity in N days" / after-stage-change follow-up tasks. | #56–58 |

### F. Reporting

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 61 | Reports | 🟡 | `BE/reports/*`: 9 built-in catalogue reports (pipeline-by-stage, deals-closing, won-lost, sales-cycle-by-owner, lead-funnel, lead-conversion-by-source, activity-by-owner, overdue-tasks, accounts-by-industry), saved reports, folders, sharing, periods; record visibility applied. | No custom report builder (choose entity, columns, filters, grouping, custom fields). | #43 |
| 62 | Dashboards | ✅ | `GET /crm/dashboard/summary` home screen + user dashboards `/crm/dashboard/boards` (migration `20260905_0100`). | — | — |
| 63 | Dashboard widgets | ✅ | `crm.dashboard_components` → saved report, display CHART/TABLE/METRIC, 12-column grid. | More widget types come with #61. | #61 |
| 64 | Dashboard builder | ✅ | `FE/app/(crm)/dashboards/[id]/page.tsx` view/arrange modes; `PUT /boards/{id}/layout`. | — | — |
| 65 | Dashboard drag-and-drop | 🔴 | Arranging uses up/down buttons (deliberate accessibility choice, commented in the page). | Add drag as an enhancement; keep buttons. | #64 |
| 66 | CRM analytics | 🟡 | Dashboard summary KPIs, pipeline journey, report library. | Forecasting, trends over time, targets/quotas. | #61 |

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
| AI | `app/(crm)/ai/*`, `app/(crm)/ai-settings/*`, `components/crm/ai/*`, `features/ai/*` | `platform/ai/*`, `products/crm/market_insights/*` | `ai_prompt_versions`, research sessions/messages (`20260827_0100`, `20260903_0100`) | `test_market_insights.py`, `test_ai_provider.py`, `test_gemini_provider.py`, `test_market_insights_prompts.py` (81 tests total) |
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
search (42), Sorting (44), Saved views (45), Inline editing (47), Bulk editing
(48), Import (50), Import field mapping (51), Export (52), Kanban (53),
Kanban drag-and-drop (54), Blueprints (55), Dashboards (62), Dashboard widgets
(63), Dashboard builder (64), Permissions (68), Tenant isolation (69), Audit
logging (70), Error handling (73), Regression testing (74). **43 in total**
(Checkpoint 4 moved 31–36, 47 and 48 here — see the Checkpoint 4 section
below for what changed and what each item's remaining gaps are).

Also present, though not in the audit list: calendar, record merge, lead
conversion, lead sources, campaigns, teams/departments, invitations, password
reset, app catalogue/enablement, Market Insights.

## Partial Functionality

AI connection (1), AI provider configuration (2), AI health/status (3), AI
Account Intelligence (5), Account 360 (12), Deal stages (19), Calls (22),
Timeline (24), Emails (27), Record layouts (41), Advanced filtering (43),
Column customization (46), Bulk actions (49), Notifications (59), Reports
(61), CRM analytics (66), Roles (67), Security (71), Performance (72), E2E
testing (75). **20 in total** (Checkpoint 4 moved Form builder (31) and DnD
field ordering (33) out to Completed, and moved Record layouts (41) in from
Missing — it is real and enforced, but has no per-role assignment and cannot
target built-in fields; see Checkpoint 4 below).

## Missing Functionality

AI Account Summary (4), AI Next-Best-Action (6), AI email generation (7), AI
meeting→CRM (8), Natural-language commands (9), AI prioritization (10),
Custom modules (40), Workflow engine (56), Workflow rules (57), Workflow
actions (58), Follow-up automation (60), Dashboard DnD (65). **12 in total.**

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
| **Checkpoint 5** | Search + Reports + Dashboards + Dashboard builder | 43, 61, 65, 66 (+ 42, 62–64 regression) | Planned |
| **Checkpoint 6** | Workflows + Blueprints + Notifications + Automation | 56–60 (55 regression) | Planned |
| **Checkpoint 7** | AI Account Intelligence + AI summaries + AI next-best-action + AI email + meeting-to-CRM + natural-language CRM | 4–10 | Planned |
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

## Next Exact Step

**Checkpoint 5 — Search + Reports + Dashboards + Dashboard Builder** (audit
items 43, 61, 65, 66, plus 42/62–64 regression). Per "Recommended
Implementation Order," this is where `@dnd-kit` (now adopted, see Checkpoint
4) gets reused for dashboard widget placement, and where the report builder
needs the advanced-filter model this checkpoint's layout condition list
(`evaluate.py`'s operator set) deliberately mirrors, so filters and rule
conditions stay one mental model instead of two.
