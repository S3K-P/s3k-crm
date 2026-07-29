# S3K Enterprise Platform — Executive Summary

**Document version:** 1.0  
**Date:** 2026-07-29  
**Status:** Planning (no production code changes)  
**Evidence base:** Repository inspection + `S3K_Technical_Foundation_Plan 1.pdf`

---

## Current Application State

S3K CRM exists today as a **frontend-only prototype** inside an npm workspaces monorepo:

| Layer | State |
|-------|-------|
| **Frontend** | Next.js 16 + React 19 UI with 31 CRM routes, rich admin/AI-settings consoles |
| **Backend** | Express stub with single `GET /health` (`backend/src/index.ts`) |
| **Database** | None configured |
| **Auth** | None — no middleware, sessions, or route guards |
| **API integration** | Zero — all CRM data is in-page mock state |
| **Feature modules** | 22 `features/*/index.ts` barrels are empty stubs |

The UI demonstrates the intended CRM product surface area but **does not persist or authorize data**.

---

## Corrected Product Vision

**S3K CRM is the first product of the S3K Enterprise Platform**, not the platform itself.

- **Shared Platform Layer** — identity, organizations, RBAC, documents, audit, notifications, AI gateway, integrations
- **S3K CRM** — accounts, contacts, leads, opportunities, campaigns, activities, etc.
- **Future products** (Books, Projects, Contracts, HR, Support, AI) — architecture only in this phase

CRM must remain independently maintainable. Future products extend the platform; they must not require CRM schema changes.

---

## Recommended Architecture

### Style: Modular Monolith with Strict Product Boundaries

```
┌─────────────────────────────────────────────────────────┐
│                  S3K Backend (Monolith)                  │
│  ┌─────────────────────┐  ┌─────────────────────────┐ │
│  │  Shared Platform     │  │  S3K CRM Domain          │ │
│  │  auth, orgs, RBAC,    │  │  accounts, leads, opps,  │ │
│  │  docs, audit, notify  │  │  activities, search      │ │
│  └─────────────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   PostgreSQL 18                  Redis 7+ / R2
   (RLS tenant isolation)         (jobs, cache, files)
```

**Recommendation:** Follow the **S3K Technical Foundation Plan** — Python 3.13, FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 18 with RLS. Replace the current Express stub.

Prisma schema documents in `04-*` and `05-*` define the **logical data model**; implement as SQLAlchemy models per foundation plan.

---

## Major Frontend-to-Backend Gaps

| Gap | Impact |
|-----|--------|
| No API layer | All CRUD is local `useState` — data lost on refresh |
| No auth/RBAC enforcement | Admin roles UI is decorative |
| Duplicate inline types per page | 10+ conflicting entity definitions |
| String-based relationships | `account: 'Acme Corp'` instead of FK IDs |
| `[id]` routes ignore URL param | Detail pages show static mock regardless of ID |
| Dual navigation systems | `config/site.ts` vs `config/crm-navigation.ts` |
| Pipeline stage inconsistency | Dashboard vs Opportunities use different stage names |
| No reports route | Reports referenced in RBAC matrix but no page |
| AI settings without backend | Provider keys, prompts, agents are static |

---

## Database & Tenant Strategy

| Decision | Recommendation |
|----------|----------------|
| **Initial tenancy** | Shared database, shared schema, `organizationId` on all tenant data |
| **Enforcement** | PostgreSQL RLS + backend policy functions + request context |
| **ID strategy** | UUID v7 (time-sortable) for all primary keys |
| **Soft delete** | Yes for business entities; hard delete for sessions/tokens |
| **Account vs Customer** | Canonical entity: **Account** (B2B customer organization). "Customer" is business language only |

---

## Top Risks

1. **Backend stack drift** — Express stub conflicts with foundation plan (Python/FastAPI)
2. **CRM-as-platform anti-pattern** — temptation to put finance/project fields in CRM tables
3. **Frontend-only authorization** — roles matrix in `admin/roles/page.tsx` is not security
4. **Entity naming chaos** — Account/Contact/Lead types duplicated per page file
5. **Missing tenant context** — no organization model exists anywhere yet

---

## Immediate Engineering Actions

1. **ADR-001:** Confirm Python/FastAPI backend; retire Express stub
2. **Phase 0:** Scaffold FastAPI monorepo structure under `backend/`
3. **Normalize frontend types** — extract shared types to `features/shared/types/`
4. **Implement Shared Platform Phase 1** before any CRM business tables
5. **Configure PostgreSQL 18 + Alembic + RLS** with tenant context middleware
6. **Generate typed API client** for frontend via OpenAPI (`orval` or `openapi-typescript`)

---

## Stakeholder Decisions Required

| Decision | Owner |
|----------|-------|
| Confirm Python/FastAPI over TypeScript/NestJS/Prisma | Engineering + CTO |
| Account vs Customer canonical naming for external APIs | Product |
| Single-org vs multi-org per user at launch | Product |
| MFA required at launch or Phase 2 | Security |
| India data residency requirements | Legal/Compliance |
| AI provider selection and data handling policy | Product + Legal |

See `17-RISKS-OPEN-QUESTIONS-AND-DECISIONS.md` for full list.
