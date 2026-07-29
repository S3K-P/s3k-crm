# Current-State Frontend Assessment

**Evidence:** Repository files under `frontend/` inspected 2026-07-29.

---

## Repository Overview

| Item | Value |
|------|-------|
| Framework | Next.js 16.2 (`frontend/package.json`) |
| React | 19 |
| Styling | Tailwind CSS + CSS tokens (`frontend/app/globals.css`) |
| Monorepo | npm workspaces — `frontend/`, `backend/` |
| Route groups | `(crm)` — CRM app; `(app)` — UI starter template |

---

## Frontend Architecture

```
frontend/
├── app/
│   ├── page.tsx                    # Marketing landing
│   ├── (crm)/                      # CRM application shell
│   │   ├── layout.tsx              # CrmShell + sidebar
│   │   ├── dashboard/
│   │   ├── leads/, contacts/, accounts/, opportunities/
│   │   ├── campaigns/, meetings/, qualification/, lead-sources/
│   │   ├── admin/, ai-settings/
│   └── (app)/                      # Legacy UI starter (disconnected)
├── components/crm/                 # Shared CRM UI library
├── config/crm-navigation.ts        # Sidebar nav (authoritative for CRM)
├── config/site.ts                  # Header nav (UI starter only)
└── features/                       # 22 empty barrel stubs
```

**Fact:** CRM navigation is driven by `frontend/config/crm-navigation.ts`, not `site.ts`.

---

## Route Inventory

### CRM Routes (31 pages)

| Route | File | Module |
|-------|------|--------|
| `/dashboard` | `app/(crm)/dashboard/page.tsx` | Dashboard |
| `/lead-sources` | `app/(crm)/lead-sources/page.tsx` | Lead Sources |
| `/leads` | `app/(crm)/leads/page.tsx` | Leads |
| `/leads/[id]` | `app/(crm)/leads/[id]/page.tsx` | Lead Detail |
| `/campaigns` | `app/(crm)/campaigns/page.tsx` | Campaigns |
| `/campaigns/[id]` | `app/(crm)/campaigns/[id]/page.tsx` | Campaign Detail |
| `/meetings` | `app/(crm)/meetings/page.tsx` | Meetings |
| `/meetings/[id]` | `app/(crm)/meetings/[id]/page.tsx` | Meeting Detail |
| `/accounts` | `app/(crm)/accounts/page.tsx` | Accounts |
| `/accounts/[id]` | `app/(crm)/accounts/[id]/page.tsx` | Account Detail |
| `/contacts` | `app/(crm)/contacts/page.tsx` | Contacts |
| `/contacts/[id]` | `app/(crm)/contacts/[id]/page.tsx` | Contact Detail |
| `/opportunities` | `app/(crm)/opportunities/page.tsx` | Opportunities |
| `/opportunities/[id]` | `app/(crm)/opportunities/[id]/page.tsx` | Opportunity Detail |
| `/qualification` | `app/(crm)/qualification/page.tsx` | Qualification |
| `/qualification/[id]` | `app/(crm)/qualification/[id]/page.tsx` | Qualification Workspace |
| `/admin/*` | `app/(crm)/admin/` (9 pages) | Admin |
| `/ai-settings/*` | `app/(crm)/ai-settings/` (10 pages) | AI Settings |

### Missing Routes (referenced in nav but not implemented)

- `/admin/workflows`, `/admin/data`, `/admin/notifications` — linked in admin layout, disabled/404
- `/reports` — in RBAC matrix (`admin/roles/page.tsx`) but no route exists

---

## Feature Inventory by Module

### Leads (`frontend/app/(crm)/leads/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Data source** | `INITIAL_DATA` mock array (5 records), `useState` CRUD |
| **Types** | Inline `Lead`, `LeadStatus` |
| **Statuses** | New, Contacted, Qualified, Proposal Sent, Negotiation, Converted, Lost |
| **Table columns** | Lead Name, Company, Email, Phone, Lead Source, Owner, Status, AI Score, Last Activity, Created Date |
| **Filters** | Search (name/company/email), Status, Source |
| **Views** | Table, Kanban |
| **Form fields** | firstName*, lastName*, email, phone, company*, industry, website, companySize, source, status, priority, expectedDealSize, owner, notes |
| **Actions** | Add, Edit, Delete, Export, Import (UI only) |
| **API calls** | None |
| **Permissions** | None enforced |

### Accounts (`frontend/app/(crm)/accounts/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Data source** | `INITIAL_DATA` mock (5 records) |
| **Types** | Inline `Account`, `AccountStatus` |
| **Statuses** | Active, Churned, Onboarding, At Risk |
| **Table columns** | Account Name, Industry, Website, Primary Contact, Owner, Open Opps, Pipeline Value, Health, Last Activity, Status |
| **Form fields** | name*, website, industry, companySize, annualRevenue, address fields, owner, status, source, description |
| **Note** | UI label "Account"; copy uses "customer" in subtitles |

### Contacts (`frontend/app/(crm)/contacts/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Types** | `Contact`, `ContactStatus` (Active/Inactive) |
| **Relationship** | `account: string` — free text, not FK |
| **Table columns** | Full Name, Job Title, Account, Email, Phone, Owner, Status, Last Interaction, Relationship (aiScore) |

### Opportunities (`frontend/app/(crm)/opportunities/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Stages** | Qualification, Discovery, Proposal, Negotiation, Contract Review, Closed Won, Closed Lost |
| **Table columns** | Name, Account, Value, Stage, Prob., Close Date, Owner, AI Health, Last Activity |
| **Views** | Table, Kanban |

### Campaigns (`frontend/app/(crm)/campaigns/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Statuses** | Planning, Active, Paused, Completed, Cancelled |
| **Types** | Email, Webinar, Social Media, Event, Advertisement |
| **Evidence** | Full list + detail pages with `MOCK_RELATIONSHIPS`, `AICampaignInsights` |

### Meetings (`frontend/app/(crm)/meetings/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Statuses** | Scheduled, Completed, Cancelled, Rescheduled |
| **Types** | Online, In Person, Call |
| **Related entities** | account, contact, opportunity (all strings) |

### Qualification (`frontend/app/(crm)/qualification/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Statuses** | Unqualified, In Review, Qualified, Disqualified |
| **Frameworks** | BANT, MEDDICC, CHAMP (detail page) |
| **Fields** | budget, authority, need, timeline (BANT) |
| **Note** | Separate `QualLead` type from `Lead` — not linked by ID |

### Lead Sources (`frontend/app/(crm)/lead-sources/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **Statuses** | Active, Inactive |
| **Table columns** | Source Name, Category, Description, Lead Count, Status, Created By, Last Updated |

### Dashboard (`frontend/app/(crm)/dashboard/page.tsx`)

| Aspect | Detail |
|--------|--------|
| **KPIs (hardcoded)** | New Leads: 42, Qualified: 18, Open Opps: 27, Pipeline: $1.74M, Meetings Today: 4, Tasks Due: 5 |
| **Pipeline stages** | Prospecting, Qualification, Proposal, Negotiation, Closed Won — **differs from opportunity stages** |
| **Components** | `KpiCard`, `TaskCard`, `MeetingCard`, `PipelineStageCard`, `ActivityItem` |

### Admin (`frontend/app/(crm)/admin/`)

| Page | Mock Data |
|------|-----------|
| users | 5 users — roles: Admin, Sales Manager, Sales Rep, Marketing Lead, Support Agent |
| roles | Static V/C/E/D matrix for 11 modules |
| teams | 3 teams |
| audit-logs | 5 log entries |
| integrations | 6 integrations |
| security | MFA/password policy UI (non-functional) |

### AI Settings (`frontend/app/(crm)/ai-settings/`)

10 pages with static provider configs, agents, prompts, knowledge sources, automations. **No API keys stored; all mock.**

---

## Mock Data Inventory

| Pattern | Locations |
|---------|-----------|
| `INITIAL_DATA` | All list pages (leads, contacts, accounts, opportunities, campaigns, meetings, qualification, lead-sources, admin/users, admin/audit-logs) |
| `MOCK_*` | All `[id]` detail pages, dashboard |
| `Math.random()` scores | Generated on save for aiScore/healthScore |
| Demo rails | `components/workspace/SourcesRail.tsx`, `RecentRail.tsx` |

---

## API Inventory

**Finding:** Zero API calls in the frontend.

- No `fetch()`, `axios`, or Next.js API routes
- `features/shared/services/index.ts` — empty stub (`export {}`)
- Detail pages contain comments: *"Real app would fetch lead by id here"*

---

## Type & Interface Inventory

All entity types are **co-located in page files**, not shared:

| Entity | Defined In | Conflicts |
|--------|-----------|-----------|
| Lead | `leads/page.tsx` | vs `QualLead` in qualification |
| Account | `accounts/page.tsx` | No `Customer` type exists |
| Contact | `contacts/page.tsx` | `account` is string |
| Opportunity | `opportunities/page.tsx` | Stage names differ from dashboard |
| Meeting | `meetings/page.tsx` | vs dashboard `MeetingCard` status enum |
| AdminUser | `admin/users/page.tsx` | Same names as CRM owners |

---

## Domain Inconsistencies

1. **Account vs Customer** — Routes/types use Account; marketing copy uses "customer"
2. **Lead.Qualified ≠ Qualification.Qualified** — same word, different lifecycle stages
3. **Pipeline stages** — Dashboard (5 stages) ≠ Opportunities kanban (7 stages)
4. **Score naming** — AI Score / Relationship / Health / AI Health for similar numeric fields
5. **Person identity** — Sarah Chen appears as lead owner, contact, admin user without unified User reference
6. **Detail page routing** — `[id]` param read but mock data always returns same record

---

## Security Observations

| Issue | Location | Severity |
|-------|----------|----------|
| No authentication | Entire `(crm)` route group | Critical |
| RBAC UI only | `admin/roles/page.tsx` | Critical |
| No route guards | No middleware.ts | Critical |
| Generic user avatar | `components/crm/topbar/CrmTopbar.tsx` — letter "U" | Medium |
| AI provider config exposed in UI | `ai-settings/providers/page.tsx` | Medium (future) |

---

## Backend Requirements Summary

| Priority | Requirement |
|----------|-------------|
| P0 | Authentication, sessions, organization context |
| P0 | RBAC with backend enforcement |
| P0 | Tenant isolation on all queries |
| P1 | CRUD APIs for all CRM list/detail modules |
| P1 | Shared types + OpenAPI-generated frontend client |
| P1 | Replace mock data with API hooks |
| P2 | Dashboard aggregation endpoints |
| P2 | Global CRM search |
| P2 | Import/export |
| P3 | AI settings backend (deferred until AI phase) |

See `10-CRM-MODULE-BY-MODULE-BACKEND-PLAN.md` for per-module detail.
