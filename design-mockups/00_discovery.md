# Phase 0 — Codebase Discovery

Read-only investigation of the S3K CRM repo before any design work. This worktree's
frontend (`frontend/app/(crm)/...`) is the real, actively-developed product surface.
(Note: a separate top-level `app/(crm)/partners` + `features/crm/partners` pair exists
outside `frontend/` — this looks like leftover prototype scaffolding, not part of the
Next.js app that actually runs, since the real Next app lives entirely under `frontend/`
and has its own `app/(crm)/...` tree. Flagged, not touched.)

No `docs/references/salesforce/` directory exists in this repo — there are no
screenshots to view. Design decisions below are instead grounded in the detailed
pattern descriptions already provided in the task brief (layout, information
hierarchy, interaction model), combined with what actually exists in this codebase.
This is noted as an open question in `REVIEW.md`.

---

## 1. Frontend stack, styling, components, theme tokens, brand

- **Framework:** Next.js 16 (App Router, Turbopack dev), React 19, TypeScript 5.
- **Styling:** Tailwind CSS 3.4 (utility classes) layered on top of a small CSS-variable
  token system defined once in [frontend/app/globals.css](../frontend/app/globals.css).
  No component library (no shadcn/MUI/Ant) — everything is hand-built per page/component
  under `frontend/components/crm/*`.
- **Icons:** `lucide-react` (already an "inline SVG, drawn by hand" icon set in spirit —
  this is why the mockups also use hand-drawn inline SVG in the same line-icon style).
- **Fonts:** Inter (body, `--font-inter`) + Sora (display, `--font-sora`), both self-hosted
  via `next/font/google`, declared in [frontend/app/layout.tsx](../frontend/app/layout.tsx).
  Note: `globals.css` currently maps `--font-display` to `var(--font-sans)` rather than
  `var(--font-sora)` — Sora is loaded but not actually wired to the `.font-display` class.
  Likely an existing bug, left untouched (no production code changes in this task); the
  mockups use Sora correctly for headings to show the intended effect.
- **Theme tokens** (light → dark), from `globals.css`:
  - `--bg` `#f4f4f7` → `#0c0c12`
  - `--surface` `#ffffff` → `#15151e`
  - `--surface-2` `#f8f8fb` → `#1b1b26`
  - `--border` `#e7e7ef` → `#272733`
  - `--text` `#15131f` → `#ececf2`
  - `--muted` `#6b6880` → `#a4a2b5`
  - `--faint` `#9a97ad` → `#6d6b80`
  - `--accent` `#6d28d9` → `#a78bfa` (violet/purple — this **is** S3K's brand color)
  - `--accent-2` `#9333ea` → `#c084fc`
  - `--accent-soft` `#f0ecff` → `#221b3a`
  - Dark mode toggled via a `.dark` class on `<html>`, set pre-paint by
    `context/ThemeContext.tsx`'s `themeInitScript` (localStorage, falls back to OS preference).
- **Brand** ([frontend/config/site.ts](../frontend/config/site.ts)): mark `"S3K"`, name
  `"S3K CRM"`, tagline `"AI-First Enterprise CRM"`. Logo is `components/brand/BrandLogo.tsx`
  (a generated mark, not an uploaded image asset) — no Salesforce-style illustrated logo.
- **No existing component-library doc page** was found beyond `frontend/THEME.md` (a
  written reference) and a live `Tools → Components` route mentioned there
  (`frontend/app/(app)/tools/components`) — this is for the *other*, non-CRM `(app)`
  layout, not the CRM one. The CRM itself has no single design-system page — Phase 1 of
  this task fills that gap as a **mockup**, not a change to the real app.

## 2. Current Dashboard

- **Route:** `/dashboard` → [frontend/app/(crm)/dashboard/page.tsx](../frontend/app/(crm)/dashboard/page.tsx)
- **Layout:** greeting header ("Good morning 👋" + today's date) → 6 KPI cards
  (New Leads, Qualified, Open Opps, Pipeline Value, Meetings Today, Tasks Due) → two-column
  row (Today's Tasks list, Upcoming Meetings list) → Sales Pipeline summary (5 stage cards +
  total value) + Quick Actions (4 buttons) → Recent Activities timeline.
- **Components used:** `KpiCard`, `TaskCard`, `MeetingCard`, `PipelineStageCard`,
  `ActivityItem`, `QuickActionButton`, `SectionHeader` (all in `components/crm/cards/*`
  and `components/crm/shared/*`).
- **Data source:** 100% hard-coded mock arrays in the page file itself
  (`MOCK_TASKS`, `MOCK_MEETINGS`, `MOCK_PIPELINE`, `MOCK_ACTIVITIES`). No API calls, no
  loading/empty states, no personalization, no customize/edit mode, no currency
  localization (uses `$`, not `₹`).

## 3. Current Contacts module

- **List:** `/contacts` → [frontend/app/(crm)/contacts/page.tsx](../frontend/app/(crm)/contacts/page.tsx).
  Uses a generic `DataTable` (`components/crm/tables/DataTable.tsx`) with client-side
  search/sort/filter over a hard-coded `INITIAL_DATA` array. Columns: Full Name, Job Title,
  Account, Email, Phone, Contact Owner, Status (badge), Last Interaction, "Relationship"
  (an AI score 0–100, color-coded), row overflow menu (Edit/Delete). Toolbar: search box,
  Account filter, Status filter, Import/Export buttons (present, not wired), "Add Contact".
  No column chooser, density toggle, saved list views, bulk actions, or pagination today —
  all flagged as `PROPOSED` additions in the mockups where Salesforce's pattern calls for them.
- **Create/Edit:** a right-side **slide-over drawer** (`components/crm/dialogs/SlideDrawer.tsx`),
  not a centered modal — this is the existing S3K interaction pattern for all CRM create/edit
  forms (also used by Accounts, Leads, etc.). Sections today: Personal Information → Company
  Association → Address → CRM Information. Footer: Cancel / Save(or Update) — no "Save & New".
- **Validation today:** only a client-side guard in `handleSave()` — First Name, Last Name,
  and Email must be non-empty, or the save silently no-ops. No inline field errors, no
  duplicate detection, no error summary.
- **Detail/record page:** `/contacts/[id]` →
  [frontend/app/(crm)/contacts/[id]/page.tsx](../frontend/app/(crm)/contacts/[id]/page.tsx).
  Header (avatar initials, name, status badge, title + account, Schedule/Email/+Opportunity
  buttons) → two-column body: left = `Tabs` (Overview, Activities, Meetings, Opportunities,
  Emails, Notes, Files, Timeline — most are stub placeholders today), right rail =
  `AIPanel` (engagement score, relationship strength, sentiment, suggested next action,
  AI-written summary). This AI panel is a genuinely S3K-specific pattern (not in Salesforce)
  and is preserved in the mockup rather than replaced.

## 4. Contact data model

- **Backend reality:** `backend/app/products/crm/contacts/{models,schemas,policies}.py`
  are **placeholders** — explicit docstrings state "no tables are defined yet" / database
  models arrive with the tenant-context and RLS task. There is no live Contact API today.
- **Planned/logical schema** (the authoritative source of truth for fields, since it was
  reverse-engineered from the same frontend mock types and written up for implementation):
  [docs/architecture/05-CRM-PRISMA-SCHEMA.md](../docs/architecture/05-CRM-PRISMA-SCHEMA.md),
  `model Contact`:

  | Field | Type | Nullable | Notes |
  |---|---|---|---|
  | `id` | UUID | No | PK |
  | `organizationId` | UUID | No | tenant FK |
  | `accountId` | UUID | **Yes** | FK → Account |
  | `firstName` | String | No | |
  | `lastName` | String | No | |
  | `email` | String | Yes | |
  | `phone` | String | Yes | work phone |
  | `mobile` | String | Yes | |
  | `jobTitle` | String | Yes | |
  | `department` | String | Yes | |
  | `ownerId` | UUID | Yes | FK → User |
  | `reportingManagerId` | UUID | Yes | FK → User/Contact (ambiguous in doc — treated as internal reporting manager, matching frontend) |
  | `status` | enum `ContactStatus` | No, default `ACTIVE` | `ACTIVE \| INACTIVE` |
  | `aiScore` | Int | Yes | 0–100, "Relationship" score in the UI |
  | `preferredCommunication` | String | Yes | free text today (Email/Phone/Meeting in UI) |
  | `linkedInUrl` | String | Yes | |
  | `notes` | String | Yes | |
  | `country` / `state` / `city` / `postalCode` / `addressLine1` | String | Yes (all) | single address, no multi-address support |
  | `createdById` / `updatedById` / `createdAt` / `updatedAt` / `deletedAt` | — | — | audit/soft-delete |

  Relation: `Contact.account → Account?` (one optional FK; no many-to-many).
  No `tags` field, no `secondaryEmail`/`whatsapp`/`website` fields, no custom-field storage
  wired to Contact yet (a generic `CRMCustomField`/`CRMCustomFieldValue` system exists for
  any CRM entity type but nothing Contact-specific is seeded). No `avatarUrl`/photo field.
  **Every field referenced above is treated as REAL** in the mockups; anything beyond this
  list (tags on contacts, WhatsApp number, company lookup-with-typeahead metadata, duplicate
  rules, etc.) is marked `PROPOSED` in the form mockup and listed in `REVIEW.md`.

## 5. Navigation structure (real)

From [frontend/config/crm-navigation.ts](../frontend/config/crm-navigation.ts) — this is the
literal, single source of truth for the sidebar, so the mockups use exactly these sections
and labels (no Salesforce-style "Service"/"Marketing Cloud" top-level items invented):

| Section | Items |
|---|---|
| Overview | Dashboard |
| Pipeline | Lead Sources, Leads, Partners, Campaigns, Meetings |
| Relationships | Accounts, Contacts, Opportunities, Qualification |
| AI | AI Insights, Next Best Action |
| System | Admin, AI Settings |

Note: "Partners" is in the nav config and presumably routes to `/partners`, but no
`frontend/app/(crm)/partners` route file exists in this worktree — likely a route still to
be built, or a leftover config entry. Left as-is in the mockup nav (matches real config);
flagged in `REVIEW.md` rather than silently fixed.

Topbar today ([CrmTopbar.tsx](../frontend/components/crm/topbar/CrmTopbar.tsx)): a search
trigger that opens a ⌘K modal searching nav item labels only (not records), a theme toggle,
a notification bell (visual only, not wired), and a static avatar square showing a hard-coded
"U" initial (no real user/profile menu). No global "+" quick-create exists today — the
mockup's quick-create menu in the topbar is `PROPOSED`.

## 6. Roles / permissions affecting what a user sees

- Found a **UI-only** mock permissions matrix at
  [frontend/app/(crm)/admin/roles/page.tsx](../frontend/app/(crm)/admin/roles/page.tsx)
  listing five roles: **Admin, Sales Manager, Sales Rep, Marketing, Support**, against
  CRM modules (Dashboard, Leads, Accounts, Contacts, Opportunities, Meetings, Campaigns,
  Qualification, AI Features, Reports, Admin), with View/Create/Edit/Delete toggles.
- Backend `platform/authorization/*` exists (models/policies/service/router) — a real
  authorization subsystem — but `crm/contacts/policies.py` itself is still a placeholder
  docstring, so today nothing actually restricts Contact visibility by role.
- `docs/architecture/13-SECURITY-AND-TENANT-ISOLATION.md` confirms: "Frontend role
  visibility (`admin/roles/page.tsx`) = UX only" — i.e. role gating is intentionally a
  front-end concern layered over backend policy, not yet the backend's enforcement.
- **Mockup implication:** the Contact form's "Owner" field is shown as auto-filled/read-only
  for a regular rep and editable for Admin/Sales Manager, matching the five real role names
  above (not an invented Salesforce-style profile system).

---

---

## Addendum — Discovery for the other CRM modules

Following the Contacts review, the same read-only discovery was repeated for every other
CRM module (Accounts, Opportunities, Leads, Lead Sources, Campaigns, Meetings, Tasks,
Qualification, Partners), reading each module's real frontend mock page in
`frontend/app/(crm)/`. Findings below are the delta worth flagging beyond what §1–§6 above
already cover (every module shares the same `DataTable` + `SlideDrawer` + `FormField` +
`StatusBadge` scaffolding as Contacts, so that part isn't repeated per module).

- **All real routes exist** for Accounts, Opportunities, Leads, Lead Sources, Campaigns,
  Meetings and Qualification under `frontend/app/(crm)/`, each with its own list page and
  (except Lead Sources) an `[id]` detail page. Each already has richer data than Contacts in
  places — e.g. Accounts has `healthScore`/`source`/a full address block; Opportunities has a
  table+Kanban toggle; Leads and Opportunities both have Kanban board views.
- **Lead Sources has no `[id]` detail route at all** — clicking a row opens the edit drawer
  directly. The mockup (`11_lead_sources.html`) matches this: list + modal, no detail page.
- **Qualification is a triage queue, not a CRUD list.** There's no "create new qualification
  record" flow anywhere — real app and schema both model a `QualificationRecord` as generated
  from an existing `Lead`, not created standalone. The list page's BANT fields (budget/
  authority/need/timeline as free-text strings) and the `[id]` workspace page's 4-item boolean
  checklist are two different, non-overlapping data shapes for the same concept in the current
  frontend — a modeling inconsistency to reconcile before building the real backend for this.
  The workspace page also has a `Framework` selector (BANT/MEDDICC/CHAMP) with no
  corresponding field in `docs/architecture/05-CRM-PRISMA-SCHEMA.md`'s `QualificationRecord`.
- **Tasks has no dedicated route or page at all.** The only Task-related code is
  `frontend/components/crm/cards/TaskCard.tsx`, a presentational list-item component used by
  the Dashboard. There is no `/tasks` list, no create/edit form, no detail page today. The
  Tasks mockup (`16_tasks.html`) is therefore net-new, built directly from the backend's
  planned `Task` model in the Prisma doc, not from any existing frontend screen.
- **Partners exists only as a stale, unreachable prototype.** Its files live at repo-root
  `app/(crm)/partners/` and `features/crm/partners/*` — a different Next.js app directory
  from `frontend/app/(crm)/`, where every other real route lives. That prototype's list and
  detail pages are read-only (Add/Edit buttons present but wired to nothing), and its money
  fields are raw numbers (`totalPipelineValue: 4250000`) rather than the formatted-string
  convention every other module in `frontend/app/(crm)` uses. The Partners mockup
  (`19_partners.html`, `20_partner_detail.html`) is a from-scratch rebuild in the real design
  system, grounded in that prototype's field shape but not copied from its location or its
  number-formatting convention.
- **Campaign's detail page shows relationship-attribution metrics** (accounts created,
  pipeline value attributed, revenue attributed) that have no corresponding field on the list
  page's `Campaign` interface — would need a `CampaignMember`/attribution join in a real
  backend; shown in the mockup as read-only, not wired to any editable field.
- **Meeting's `notes` field exists in the interface and mock data but is never wired into the
  real create/edit drawer** (only `agenda` is editable there) — a pre-existing form/interface
  mismatch in the current frontend, left as-is in the mockup (one editable "Agenda" field, no
  separate Notes field on the Meeting form).

## Files referenced
- `frontend/app/globals.css`, `frontend/THEME.md`, `frontend/config/site.ts`,
  `frontend/config/crm-navigation.ts`
- `frontend/app/(crm)/dashboard/page.tsx`, `frontend/app/(crm)/contacts/page.tsx`,
  `frontend/app/(crm)/contacts/[id]/page.tsx`, `frontend/app/(crm)/admin/roles/page.tsx`
- `frontend/components/crm/shared/CrmShell.tsx`, `.../sidebar/CrmSidebar.tsx`,
  `.../topbar/CrmTopbar.tsx`, `.../dialogs/SlideDrawer.tsx`
- `backend/app/products/crm/contacts/*.py` (placeholders)
- `docs/architecture/05-CRM-PRISMA-SCHEMA.md`, `docs/architecture/13-SECURITY-AND-TENANT-ISOLATION.md`
