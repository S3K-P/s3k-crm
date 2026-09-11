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

**75 features audited: 33 ✅ COMPLETE · 22 🟡 PARTIAL · 20 🔴 MISSING.**

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
| 12 | Account 360 | 🟡 | `FE/app/(crm)/accounts/[id]/page.tsx` shows details, address, custom fields, contacts, opportunities, activity timeline, emails, notes, attachments. | No summary header (open pipeline value, won revenue, last activity, open tasks, next meeting). No tasks/upcoming panel. No AI summary. Needs an aggregate endpoint (e.g. `GET /crm/accounts/{id}/overview`). | #4, #16, #21, #24 |
| 13 | Contacts | ✅ | `BE/contacts/*`; CRUD, export, merge; `FE/app/(crm)/contacts/*`. | — | — |
| 14 | Contacts ↔ Accounts | ✅ | `crm.contacts.account_id`; `AccountContactsPanel` (`FE/components/crm/shared/RelatedLists.tsx`); create-from-account prefill. | — | — |
| 15 | Deals | ✅ | `BE/opportunities/*` (CRUD, export, stage change, reopen, history). | — | — |
| 16 | Deals ↔ Accounts | ✅ | `crm.opportunities.account_id` (NOT NULL); `AccountOpportunitiesPanel`, `ContactOpportunitiesPanel`. | — | — |
| 17 | Primary contacts | 🟡 | `accounts.primary_contact_id`, `opportunities.primary_contact_id`; `POST /crm/contacts/{id}/primary`; client `makeContactPrimary` in `FE/features/crm/contacts/index.ts`. | The UI never calls `makeContactPrimary`, and the account page doesn't show the primary contact. Add "Make primary" to the account's contacts panel and show a badge. | #12, #14 |
| 18 | Deal pipeline | ✅ | Per-tenant `crm.pipeline_stages` provisioned at signup; Kanban + table views; `FE/app/(crm)/pipeline-journey/*`. | — | — |
| 19 | Deal stages | 🟡 | Stage moves via `POST /crm/opportunities/{id}/stage` (state machine + blueprint), `/reopen`, `/history`; `GET /stages`. | Stages are **read-only** for tenants (`admin/crm-settings/page.tsx` says so). Need stage CRUD/reorder/probability admin. | #18, #55 |
| 20 | Activities | ✅ | `BE/activities/*`; types CALL/EMAIL/MEETING/NOTE/TASK; polymorphic `related_entity_*`. | — | — |
| 21 | Tasks | ✅ | `BE/tasks/*` (status machine, status counts, due-date index); `FE/app/(crm)/tasks/page.tsx`; due reminders. | — | — |
| 22 | Calls | 🟡 | Logged as `Activity(type=CALL)` with `outcome` text. | No call-specific fields (direction, duration, result picklist), no "Log call" quick action, no calls list. Telephony is out of scope. | #20 |
| 23 | Meetings | ✅ | `crm.meetings` (type, start/end, location, link, agenda, participants, reminder); `FE/app/(crm)/meetings/*`; calendar; reminders. | — | — |
| 24 | Timeline/activity history | 🟡 | `GET /crm/activities/timeline` + `ActivityTimelinePanel` on account/contact/lead/deal pages. | Activities only. Emails, notes, stage changes, field edits and attachments are separate panels, not one merged chronological stream. | #20, #25–27, #70 |
| 25 | Notes | ✅ | `BE/notes/*` (visibility enum); `NotesPanel`. | — | — |
| 26 | Files/attachments | ✅ | `PF/documents/*` (pre-signed MinIO/R2 URLs, validation, record-access inversion); `AttachmentsPanel`. | — | — |
| 27 | Emails/email history | 🟡 | Phase D: compose, drafts, templates with placeholders, threads, outbox delivery, per-record `EmailsPanel`, delivery log. | Outbound only: no inbound capture (IMAP/Gmail/Outlook sync, BCC-dropbox). Add inbound later; no rebuild. | #24 |

### C. CRM Configuration / Form Builder

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 28 | Custom fields | ✅ | `BE/custom_fields/*` (JSONB `custom_fields` column on 5 entities; validation in `TenantScopedService` via `shared/custom_field_hook.py`); `FE/app/(crm)/admin/custom-fields/page.tsx`; `CustomFieldInputs` on create/edit forms; `CustomFieldsPanel` on detail pages. | — | — |
| 29 | Field types | ✅ | 12 types: TEXT, TEXTAREA, NUMBER, DECIMAL, DATE, DATETIME, BOOLEAN, EMAIL, URL, PHONE, PICKLIST, MULTI_PICKLIST. | Optional additions later: currency, lookup, formula, auto-number. | — |
| 30 | Picklists | ✅ | `crm.picklists`, `crm.picklist_options` (value/label, position, active, default); `/crm/picklists`. | — | — |
| 31 | Form builder | 🟡 | Field definitions admin (create/edit/deactivate/reorder). Custom fields render in one flat block after the built-in fields. | No layout designer: built-in fields are hardcoded in each page's form. | #34, #41 |
| 32 | Drag-and-drop form editing | 🔴 | — | Layout canvas with DnD (no DnD library installed today). | #31, #34, #41 |
| 33 | Drag-and-drop field ordering | 🟡 | Ordering works through `POST /crm/custom-fields/reorder` + up/down buttons. | Add drag, keeping the buttons for keyboard access. | #32 |
| 34 | Sections | 🔴 | — | Layout model with sections. | #41 |
| 35 | Section ordering | 🔴 | — | Part of the layout model. | #34 |
| 36 | Conditional field visibility | 🔴 | — | Rules (field X shown when field Y = v) evaluated on the client for display **and** on the server for required-ness. | #34, #41 |
| 37 | Required/optional fields | ✅ | `is_required` on custom fields (enforced server-side on create; inactive fields exempt). Built-in required fields enforced by Pydantic schemas. | Per-layout required overrides come with #41. | — |
| 38 | Default values | ✅ | `custom_field_definitions.default_value` (coerced like input), picklist `is_default`. | — | — |
| 39 | Field validation | ✅ | `min_value`/`max_value`, `min_length`/`max_length`, RE2-safe `pattern`; `custom_fields/validation.py`; `tests/unit/test_custom_field_validation.py`. | — | — |
| 40 | Custom modules | 🔴 | `CrmEntityType` is a closed enum of 5 types. | New entity kind with dynamic storage, permissions, list/detail UI. Large: schedule late. | #28, #41, #68 |
| 41 | Record layouts | 🔴 | — | `crm.record_layouts` (entity, sections, field placement, per-role assignment) + renderer replacing the hardcoded forms. | #28 |

### D. Record Management

| # | Feature | Status | Existing Implementation | Missing/Required Work | Dependencies |
|---|---|---|---|---|---|
| 42 | Global search | ✅ | `GET /crm/search` (4 entities, tsvector, permission filtered in-query, migration `20260826_0100`); `FE/components/crm/topbar/CommandPalette.tsx`; `test_search_performance.py`. | — | — |
| 43 | Advanced filtering | 🟡 | Per-list filter params + typed custom-field filters (`custom_fields/filters.py`); filters persist in saved views. | No multi-condition (AND/OR, operators) filter builder UI/API. | #45 |
| 44 | Sorting | ✅ | `sort_by`/`sort_dir` on lists, custom-field sort for sortable types; `DataTable` sorting. | — | — |
| 45 | Saved views | ✅ | `BE/views/*` (private/shared, default, 404-not-403 for others' private views); `SavedViewPicker` on accounts/contacts/leads/opportunities. | — | — |
| 46 | Column customization | 🟡 | `crm.saved_views.columns` is stored. | No column chooser; `SavedViewPicker` saves filters/sort only, and tables ignore `columns`. | #45 |
| 47 | Inline editing | 🔴 | — | Editable cells in `DataTable` calling the existing `PATCH` endpoints (which already validate). | — |
| 48 | Bulk editing | 🔴 | — | `POST /crm/{entity}/bulk-update` (per-record permission + visibility + custom-field validation, one audit entry each). | #49 |
| 49 | Bulk actions | 🟡 | Row multi-select on accounts/contacts/leads, used only to launch **merge**. | Bulk delete, assign owner, add to campaign, export selected. | #48 |
| 50 | Import | ✅ | `BE/imports/*`: CSV preview + commit for leads, accounts, contacts; row errors; audit; `FE/components/crm/import/ImportWizard.tsx`. | Opportunities/custom fields as import targets are not supported. | — |
| 51 | Import field mapping | ✅ | Mapping step (CSV header → field) in the wizard; `mapping` JSON validated in `imports/router.py`. | Map to custom fields; saved mapping templates. | #28 |
| 52 | Export | ✅ | `GET /crm/{accounts,contacts,leads,opportunities}/export` (CSV-injection safe, `shared/csv_export.py`); `ExportButton`. | — | — |
| 53 | Kanban | ✅ | `FE/components/crm/kanban/KanbanBoard.tsx` on leads (by status) and opportunities (by stage); moves via row actions through the state-machine endpoints. | — | — |
| 54 | Kanban drag-and-drop | 🔴 | Board has no drag handlers. | Add DnD calling the same `status`/`stage` endpoints, reverting on 422 (blueprint/state-machine refusal). | #53, #55 |

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
Deals↔Accounts (16), Deal pipeline (18), Activities (20), Tasks (21),
Meetings (23), Notes (25), Files/attachments (26), Custom fields (28), Field
types (29), Picklists (30), Required/optional (37), Default values (38), Field
validation (39), Global search (42), Sorting (44), Saved views (45), Import
(50), Import field mapping (51), Export (52), Kanban (53), Blueprints (55),
Dashboards (62), Dashboard widgets (63), Dashboard builder (64), Permissions
(68), Tenant isolation (69), Audit logging (70), Error handling (73),
Regression testing (74). **33 in total.**

Also present, though not in the audit list: calendar, record merge, lead
conversion, lead sources, campaigns, teams/departments, invitations, password
reset, app catalogue/enablement, Market Insights.

## Partial Functionality

AI connection (1), AI provider configuration (2), AI health/status (3), AI
Account Intelligence (5), Account 360 (12), Primary contacts (17), Deal stages
(19), Calls (22), Timeline (24), Emails (27), Form builder (31), DnD field
ordering (33), Advanced filtering (43), Column customization (46), Bulk actions
(49), Notifications (59), Reports (61), CRM analytics (66), Roles (67), Security
(71), Performance (72), E2E testing (75). **22 in total.**

## Missing Functionality

AI Account Summary (4), AI Next-Best-Action (6), AI email generation (7), AI
meeting→CRM (8), Natural-language commands (9), AI prioritization (10), DnD form
editing (32), Sections (34), Section ordering (35), Conditional visibility (36),
Custom modules (40), Record layouts (41), Inline editing (47), Bulk editing (48),
Kanban DnD (54), Workflow engine (56), Workflow rules (57), Workflow actions
(58), Follow-up automation (60), Dashboard DnD (65). **20 in total.**

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
| **Checkpoint 2** | Account 360 + Contacts + Deals + relationships | 12, 17, 19 (stage admin), 11/13–16 regression | Planned |
| **Checkpoint 3** | Activities + Timeline + Notes + Files + Email CRM | 22, 24, 27 (+ 20, 25, 26 regression) | Planned |
| **Checkpoint 4** | Form builder + drag/drop + custom fields + conditional fields + Kanban + bulk/inline editing + import mapping | 31–36, 41, 46–49, 51, 54 | Planned |
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

## Next Exact Step

**Checkpoint 2: Account 360 + Contacts + Deals + relationships** (audit items
12, 17, 19; regression on 11/13–16). See "Recommended Implementation Order"
above. Suggested first task: the aggregate `GET /crm/accounts/{id}/overview`
endpoint (summary header: open pipeline value, won revenue, last activity,
open tasks, next meeting) that #12 calls for, since the frontend work for
Account 360 and the "Make primary" contact action (#17) both build on it.
