# Phase 3 — Review Pack

Review package for the Home Dashboard and Contacts module redesign. All deliverables are
static HTML in `/design-mockups/`; no application code was touched. See
[00_discovery.md](00_discovery.md) for what was found in the codebase before any design
work started, and [index.html](index.html) to browse every mockup.

---

## 0. Revision — color palette (post-review feedback)

The first pass used S3K's actual shipped violet accent (`#6d28d9`, from `frontend/app/globals.css`)
plus a different bright accent color per card/icon/avatar (emerald, sky, pink, amber, teal…) for
quick visual variety. Feedback on review: it read as "too fancy" for an enterprise tool — too many
competing colors. Revised, by explicit direction, to:

- **One primary accent across the whole system**: a deep navy/slate blue (`#1f4e79` light mode /
  `#6f9bc4` dark mode) — **this is a proposed brand change**, not a reflection of S3K's real
  shipped accent, which is still violet today. Flagging this clearly rather than silently treating
  navy as "the real S3K color."
- **Neutral grays with no purple cast** for every surface/border/text token (previously these had
  a faint violet tint inherited from the accent).
- **One treatment for every icon tile and avatar**: a muted slate background (`--surface-3`) with
  the single accent color for the icon/initials — no more per-card rainbow gradients (emerald for
  Contacts, sky for Accounts, pink for Campaigns, etc.).
- **Muted semantic colors**, used only for actual status communication (badges: Active/At Risk/
  Lost/etc.) — never decoratively. These were desaturated too (e.g. danger red went from a bright
  `#dc2626` fire-engine red to a muted brick `#b3362b`).
- The dashboard's pipeline funnel keeps *some* color progression (light→dark blue through the
  stages, green for Closed Won) since that's functional data differentiation in a chart, not
  branding — but it's now a coherent one-hue-family progression instead of five unrelated colors.

This was a systematic token-level change (`shared/tokens.css`, `shared/shell.css`) plus stripping
~70 inline color overrides across every mockup file, so it applies uniformly everywhere, including
pages built before this feedback (Contacts, Dashboard) without those files needing individual edits.

**Revision 3** — the muted navy from Revision 2 then read as *dull*. Three concrete directions
(single vibrant accent, two-tone cool+warm, per-module color-coding) were put in front of the user
as a side-by-side comparison artifact rather than guessed a third time; **"Option A — Vibrant
Indigo"** was chosen: same one-accent-everywhere restraint as Revision 2, just a richer, more
saturated indigo (`#4f39c9` light / `#8b7ae8` dark) instead of the muted navy. The dark sidebar also
picked up a matching indigo tint (`#161327`, border `#2a2347`) instead of neutral slate, and the
dashboard funnel chart's progression was re-tuned to the indigo family (light lavender → indigo →
green for Closed Won) for the same reason. Still a token-level change only — `shared/tokens.css`
and `shared/shell.css` — so it applies everywhere uniformly, same as Revision 2.

**Revision 4 (briefly applied, then reverted)** — a follow-up message was misread as a request to
extend the comparison artifact's "Option C" (per-module color-coding) on top of the chosen indigo
accent: every module got its own fixed identity color across sidebar nav, header icons, dashboard
cards and detail-page avatars (ten new `--mod-{module}` token pairs in `shared/tokens.css`). The
user clarified the actual choice was plain **Option A** — one indigo accent everywhere, no
per-module colors — so this was fully reverted: the `--mod-*` tokens removed, every inline
per-module style stripped back to the neutral/indigo default, and the sidebar nav tinting logic
removed from `shared/shell.js`. Current state is exactly Revision 3 (vibrant indigo, single accent
everywhere) with nothing else layered on top.

---

## 1. Summary of design decisions

**What was adapted from Salesforce Lightning, and how it was changed:**

| Salesforce pattern | What we kept (the mechanism) | What we changed (so it isn't Salesforce) |
|---|---|---|
| Fixed left nav, icon + label, collapsible | Information architecture: grouped sections, active-state highlight, collapse-to-icons | Used S3K's **real** 5 nav sections/14 items from `crm-navigation.ts` verbatim — no "Service Cloud"/"Marketing Cloud" style modules invented. Dark navy sidebar with violet active state, not Salesforce's white/blue. |
| Global header: search · utility icons · avatar | Centered wide search with ⌘K hint, notification bell, avatar, quick-create | Original S3K violet gradient mark instead of a cloud logo; quick-create menu limited to the 4 object types S3K actually models (Contact/Account/Opportunity/Lead). |
| Two-column card grid, each card with view-selector + New + overflow + footer "View Report"/"As of" | The card anatomy and footer metadata pattern | Added a KPI strip above the grid (Salesforce's Home lacks one) using ₹ lakh/crore formatting; cards reflect S3K's actual entities (Leads, Deals, Contacts, Pipeline, Tasks, Recent Records, Activity Timeline) instead of Salesforce's Cases/Priority widget, which S3K has no equivalent for. |
| Dismissible "discovery" banner | The dismiss-and-it's-gone interaction | Original copy ("There's more to see here"), links to S3K's own AI Insights module instead of a Trailhead-style prompt. |
| "Customize Home Page" — swap/remove cards | Drag-handle + remove-card affordance in a toggled edit mode | Simplified to a single customize toggle rather than a separate settings page; no illustration library borrowed. |
| Persistent bottom "To Do List" utility bar | Collapsed bar pinned to the viewport, expands upward | Restyled as a floating rounded card matching S3K's card language, not a full-width Salesforce-grey bar. |
| List view: switcher + pin, metadata line, toolbar, sortable table, row hover actions | The whole interaction model — it was genuinely missing from S3K's Contacts page and is a real gap (see §3) | Columns and data are 100% S3K's real Contact fields (plus one clearly badged proposed field, Tags) — no Salesforce-specific columns like "Lead Source" shoehorned in. |
| Create/edit modal: grouped sections, sticky footer (Cancel/Save & New/Save), compound address, lookup-with-create, owner auto-fill | Section grouping, sticky footer actions, lookup-with-inline-create, auto-filled read-only owner for non-admins | S3K **already uses a right-side slide drawer**, not a centered modal, for every create/edit flow today (Contacts, Accounts, etc. — see discovery §3). We built the Salesforce-style centered modal as the primary mockup per the brief, **and** kept the form content identical in a full-page variant, but flagged in §3 below that adopting a centered modal is itself a UX-pattern change from what S3K ships today, not just a reskin. India-first address order (Country→State→City→PIN→Street) replaces the US-centric State/Zip pattern. Duplicate-detection banner and inline validation/error-summary did not exist in S3K's form at all — both are new, grounded in the existing `handleSave()` guard that silently no-ops today. |
| Record page: header + quick actions + tabs + right rail | Header anatomy, tab strip, two-column (main + rail) layout | Quick actions include **WhatsApp** (flagged proposed) alongside Call/Email, reflecting India-first channels. The right rail keeps S3K's existing **AI Relationship panel** (engagement score, sentiment, suggested next action) — a real, already-shipping S3K pattern with no Salesforce equivalent — rather than replacing it with a generic "related lists" rail. |

**Visual identity:** every color, radius, shadow and font in `design-system.html` is
either the real token from `frontend/app/globals.css` (violet `#6d28d9`/`#a78bfa`,
Inter + Sora) or a semantic extension in the same family. No Salesforce blue (`#0176D3`),
no Salesforce Sans, no cloud/mascot iconography — icons are hand-drawn inline SVG in a
lucide-compatible line style, matching the `lucide-react` icon set S3K already ships.

---

## 2. Field mapping table

Source of truth: `docs/architecture/05-CRM-PRISMA-SCHEMA.md` `model Contact` (the planned
schema — the backend tables themselves don't exist yet, see discovery §4).

| Salesforce field (reference pattern) | Current S3K field (`model.field`) | Proposed S3K field | Type | Required | Notes |
|---|---|---|---|---|---|
| First Name | `Contact.firstName` | — | String | **Yes** | |
| Last Name | `Contact.lastName` | — | String | **Yes** | |
| Account Name (lookup) | `Contact.accountId` → `Account` | — | UUID FK, nullable | No | Rendered as a type-ahead lookup with inline "create new company" in the mockup |
| Title | `Contact.jobTitle` | — | String, nullable | No | |
| Department | `Contact.department` | — | String, nullable | No | |
| Email | `Contact.email` | — | String, nullable | Treated as **required** in the mockup | Real schema allows null; S3K's own `handleSave()` already treats it as required today — mockup keeps that behavior |
| Phone | `Contact.phone` | — | String, nullable | No | Rendered with a +91 country-code prefix (display-only; schema has no separate country-code column) |
| Mobile | `Contact.mobile` | — | String, nullable | No | Same +91 prefix treatment |
| Reports To (lookup) | `Contact.reportingManagerId` | — | UUID, nullable | No | Rendered as free text in the mockup (matches current frontend behavior); a real lookup would need this to become a proper FK |
| Owner | `Contact.ownerId` | — | UUID FK → User, nullable | No | Auto-filled read-only for the signed-in user; editable dropdown only when "View as" = Admin/Sales Manager in the demo, matching the 5 real roles in `admin/roles/page.tsx` |
| Mailing Country | `Contact.country` | — | String, nullable | No | Defaulted to **India** in the mockup (brief: India-first) |
| Mailing State/Province | `Contact.state` | — | String, nullable | No | Rendered as an Indian-states `<select>`; schema stores free text today, not an enum |
| Mailing City | `Contact.city` | — | String, nullable | No | |
| Mailing Zip/Postal Code | `Contact.postalCode` | — | String, nullable | No | Mockup adds a 6-digit hint/pattern for Indian PIN codes — **not enforced by the schema today** |
| Mailing Street | `Contact.addressLine1` | — | String, nullable | No | Schema has one address line, no `addressLine2` |
| Description (Salesforce "Get in Touch"/notes section) | `Contact.notes` | — | String, nullable | No | |
| — (no direct equivalent) | `Contact.aiScore` | — | Int, nullable | No | Shown read-only as "Relationship" in list/detail — **not** exposed as an editable form field, since it's AI-computed |
| — (no direct equivalent) | `Contact.preferredCommunication` | — | String, nullable | No | S3K-specific; kept as a free `<select>` (Email/Phone/Meeting) matching current frontend |
| — (no direct equivalent) | `Contact.linkedInUrl` | — | String, nullable | No | |
| — (no direct equivalent) | `Contact.status` | — | enum `ACTIVE`\|`INACTIVE` | No, default Active | |
| Lead Source (not on Contact in this schema) | — | — | — | — | Not modeled on `Contact` at all (only on `Lead`/`Campaign`); correctly omitted from the form |
| — | — | **`whatsapp`** (PROPOSED) | String, nullable | No | India-first channel; would need a schema column or reuse `mobile` with a channel flag |
| — | — | **`tags`** (PROPOSED) | String[] via `CRMEntityTag` (generic system already exists for other entities) | No | Used in the list/detail mockups; `CRMTag`/`CRMEntityTag` tables already exist in the schema for other entity types, so this is "wire it up," not "invent it" |
| — | — | **`gstin`** (PROPOSED, example only) | via generic `CRMCustomField`/`CRMCustomFieldValue` | No | Shown as a concrete example of the existing generic custom-field system applied to an India-specific use case — not a dedicated column |

---

## 3. Gaps — what S3K lacks today that the mockups assume

1. **No live Contact backend at all.** `backend/app/products/crm/contacts/{models,schemas,policies}.py` are placeholders. Every field above is "planned," not shipping — the whole module is currently 100% mock data on the frontend.
2. **Create/edit pattern mismatch.** S3K ships a right-side slide drawer for all create/edit today, not a centered modal. The modal mockup matches the brief's Salesforce-pattern request, but adopting it for real would change an established S3K interaction pattern used by Accounts, Leads, etc. — worth a deliberate decision, not a silent swap.
3. **No duplicate-detection logic anywhere in the codebase.** The mockup's banner is pure UI; there's no matching rule, no backend check, no "merge" flow behind it.
4. **No list-view infrastructure.** Saved/pinned views, column chooser, density toggle, bulk actions, and pagination don't exist for Contacts (or any CRM list) today — the real page is a single hard-coded table over one in-memory array with client-side search/sort only.
5. **No role enforcement on the backend.** `admin/roles/page.tsx` is a UI-only mock matrix; `contacts/policies.py` is an empty placeholder. The mockup's "Owner is read-only unless Admin/Sales Manager" behavior has nothing enforcing it server-side today.
6. **Dashboard has zero data wiring.** Every dashboard widget (KPIs, lists, pipeline funnel, activity feed) is hard-coded mock arrays in `dashboard/page.tsx`; there's no dashboard API, no personalization/"Customize Home" persistence, no empty/loading states today.
7. **`/partners` nav entry with no route.** `crm-navigation.ts` lists Partners under Pipeline, but `frontend/app/(crm)/partners` doesn't exist in this worktree — either a route still to be built or stale config.
8. **Proposed fields need real homes.** `tags` can reuse the existing generic `CRMEntityTag` system (low effort). `whatsapp` needs a schema decision (new column vs. a "channel" flag on `mobile`). `gstin` is deliberately shown as a generic custom field rather than a dedicated column, to avoid over-fitting the schema to one example.
9. **India-specific validation is cosmetic only.** The 6-digit PIN code hint and State dropdown are UI affordances in the mockup; nothing validates PIN/phone format today, and `state`/`country` are free-text columns, not constrained lists.

---

## 4. Open questions for the product owner

1. **No Salesforce reference screenshots were found** at `docs/references/salesforce/` (the directory doesn't exist in this repo). This review was built from the brief's own detailed pattern descriptions plus the existing S3K codebase. If there's a specific Salesforce org/screenshots you had in mind, we should compare directly before building anything.
2. **Modal vs. slide drawer**: should Contacts (and eventually other objects) move to the centered-modal pattern shown here, or should the brief's modal request instead be reinterpreted as "make the existing slide drawer this much better" (sections, validation, duplicate detection, Save & New) while keeping the drawer shell? This is the single biggest interaction-pattern decision in the whole exercise.
3. **Is `aiScore`/"Relationship" meant to stay AI-only** (read-only, computed), or should reps be able to see/override the inputs behind it anywhere in the UI?
4. **Tags**: confirm it's acceptable to implement via the existing generic `CRMEntityTag` tables rather than a dedicated `Contact.tags` column.
5. **WhatsApp**: is this a real near-term channel S3K wants to support (own number provisioning, Business API), or just a "nice to have" quick-action button for now?
6. **Owner reassignment permissions**: the mockup ties editable-Owner to Admin/Sales Manager roles from the existing mock matrix — confirm that's the intended real rule once `contacts/policies.py` is implemented.
7. **`/partners` route**: build it, or remove from nav for now?

---

## 5. Suggested implementation order (not to be started now)

1. **Contact backend**: implement the real `models.py`/`schemas.py`/`repository.py`/`service.py` for Contacts per the Prisma doc, with RLS/tenant isolation (per discovery, this needs the forced-RLS pattern already used elsewhere in the codebase).
2. **List view essentials**: server-side search/sort/pagination for Contacts; this unblocks the list mockup's toolbar before anything fancier (saved views, column chooser) is worth building.
3. **Form validation + duplicate detection**: add real required-field validation and an email/phone duplicate check to the existing slide-drawer form first — independent of the modal-vs-drawer decision, and the highest-value, lowest-risk piece of this mockup.
4. **Tags via `CRMEntityTag`**: wire the existing generic tag tables into Contacts create/edit/list/detail.
5. **Dashboard data wiring**: replace the dashboard's mock arrays with real endpoints one card at a time (My Contacts and Tasks first, since those modules are closest to shipping); add empty/loading states while doing so.
6. **Role enforcement**: implement `contacts/policies.py` against the five real roles, then make the Owner-field UI in the form actually reflect server-enforced permissions instead of a client-side role toggle.
7. **Modal vs. drawer decision** (from §4.2) should happen before any of the above gets a new create/edit UI shell, since it affects every object, not just Contacts.
8. **Dashboard customize-mode persistence**: only after the above, since it needs a place to store each user's card layout.

---

---

## Addendum — Other CRM modules (Accounts, Opportunities, Leads, Lead Sources, Campaigns, Meetings, Tasks, Qualification, Partners)

Built as a direct follow-on to Contacts, at the user's request, same quality bar: real
S3K fields grounded against each module's actual frontend page (see `00_discovery.md`
addendum) or the planned Prisma schema where no frontend page exists, India-first mock
data, `PROPOSED` badges on anything not in the real model today.

**Scope decision made for this batch:** instead of mirroring Contacts' exact 4-file split
(separate list / form-modal+full-page / detail), each new module uses a **2-file pattern**
— list view with the create/edit modal built into the same page (list+form), plus a
separate detail page where S3K's real app has one. This matches how these flows actually
get used (open "New X" from the list, don't navigate to a dedicated form page) and roughly
halves the file count without losing any interaction richness. Lead Sources and Tasks have
no detail page (matching Lead Sources' real behavior; Tasks is a lightweight entity with no
real precedent either way). Qualification has no create-modal (matching the real triage-queue
flow — see `00_discovery.md` addendum).

**Field mapping table (new modules):**

| Module | Real S3K field source | Required fields (real app) | Proposed additions in mockup |
|---|---|---|---|
| Accounts | `Account` interface, `frontend/app/(crm)/accounts/page.tsx` | Name only | None — form matches the real drawer's fields 1:1 |
| Opportunities | `Opportunity` interface, `.../opportunities/page.tsx` | Name, Account | None |
| Leads | `Lead` interface, `.../leads/page.tsx` | First Name, Last Name, Company | None |
| Lead Sources | `LeadSource` interface, `.../lead-sources/page.tsx` | Name, Category | None |
| Campaigns | `Campaign` interface, `.../campaigns/page.tsx` | Name, Budget | None |
| Meetings | `Meeting` interface, `.../meetings/page.tsx` | Title, Date | None |
| Tasks | Backend `Task` model (Prisma doc) + `TaskCard.tsx` | Title, Due Date (mockup's own choice — no real form to copy) | Whole module is proposed (no real route) |
| Qualification | `QualLead` interface + `[id]` workspace's checklist, `.../qualification/page.tsx` | N/A — no create form | `Framework` selector (BANT/MEDDICC/CHAMP) exists in the frontend already but not in the Prisma schema — flagged, not newly proposed |
| Partners | `features/crm/partners/types.ts` (stale prototype) | N/A — prototype has no working form | Whole module rebuilt from scratch in the real design system; `Linked Account` field marked proposed since the prototype's FK relation isn't in the main schema doc |

**Gaps specific to these modules** (in addition to §3 above):
1. None of these modules have a real backend either — same placeholder-only state as Contacts (`backend/app/products/crm/{accounts,opportunities,leads,...}` were not inspected in this pass but are presumed to follow the same placeholder pattern established for `contacts/`).
2. Opportunities and Leads both have real Kanban board views in the current frontend (`table+kanban` toggle) that this mockup batch did not rebuild — the list pages include a visual "Board view" button as a placeholder affordance, not a working Kanban. Worth a follow-up pass if board view matters for the review.
3. Tasks and Partners are **net-new or net-rebuilt modules** with no real route to compare against — treat their every field as a proposal, not a confirmed requirement, until validated against actual backend/product decisions.
4. The nav now routes Lead Sources, Leads, Partners, Campaigns, Meetings, Tasks, Accounts, Opportunities and Qualification to real pages instead of the `#` placeholders the original Contacts-only batch left in `shared/shell.js`. **Tasks was added as a new sidebar entry** (under "Pipeline", next to Meetings) that does not exist in the real `crm-navigation.ts` today — confirm placement before building for real.

**Open questions (additional):**
1. Should Opportunities/Leads keep their real Kanban board views in a future mockup pass, or is the table view sufficient going forward?
2. Qualification's two conflicting BANT data shapes (list page's free-text fields vs. workspace page's boolean checklist) need to be reconciled into one model before any real backend work starts there.
3. ~~Partners: confirm whether this becomes a real `frontend/app/(crm)/partners` route...~~ **Decided:** Partners stays out of the nav for now. The `19_partners.html`/`20_partner_detail.html` mockup files are kept on disk for reference, but `shared/shell.js`'s `NAV` array no longer lists Partners, so it doesn't appear in the sidebar or ⌘K search on any page. Revisit when/if it's actually prioritized.
4. Tasks: confirm whether it should be its own top-level nav item (as built here) or stay dashboard-only, which is how S3K works today.

## Files created in this review

- `00_discovery.md` — Phase 0 codebase discovery (+ addendum for the other modules)
- `design-system.html` — Phase 1 design system reference
- `01_dashboard.html` — Home Dashboard
- `02_contacts_list.html`, `03_contact_form.html`, `04_contact_detail.html` — Contacts (original 4-file pattern: list / form-modal+full-page / detail)
- `05_accounts.html`, `06_account_detail.html` — Accounts
- `07_opportunities.html`, `08_opportunity_detail.html` — Opportunities
- `09_leads.html`, `10_lead_detail.html` — Leads
- `11_lead_sources.html` — Lead Sources (no detail page, matches real app)
- `12_campaigns.html`, `13_campaign_detail.html` — Campaigns
- `14_meetings.html`, `15_meeting_detail.html` — Meetings
- `16_tasks.html` — Tasks (proposed module, no detail page)
- `17_qualification.html`, `18_qualification_workspace.html` — Qualification (triage queue, no create modal)
- `19_partners.html`, `20_partner_detail.html` — Partners (proposed, rebuilt from a stale prototype)
- `index.html` — gallery linking everything above
- `shared/tokens.css`, `shared/shell.css`, `shared/shell.js`, `shared/app.js` — design tokens, base components and the app-shell renderer (sidebar/topbar/breadcrumb) shared by every page
- `shared/views.css`, `shared/form-helpers.js` — shared list/form-modal/detail CSS and generic lookup/duplicate-check/validation JS used by every module built after Contacts (Contacts' own 02–04 files keep their original embedded styles, untouched)
- `shared/contacts-data.js`, `shared/accounts-data.js`, `shared/opportunities-data.js`, `shared/leads-data.js`, `shared/lead-sources-data.js`, `shared/campaigns-data.js`, `shared/meetings-data.js`, `shared/tasks-data.js`, `shared/qualification-data.js`, `shared/partners-data.js` — one mock-data file per module, referencing the same people/company roster across modules for consistency
- `REVIEW.md` — this file
