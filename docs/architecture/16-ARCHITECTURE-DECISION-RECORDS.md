# Architecture Decision Records

**Format:** Status = Proposed (pending stakeholder approval)

---

## ADR-001: Modular Monolith Architecture

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Context** | Multiple S3K products planned; small team; no backend exists yet |
| **Decision** | Modular monolith with Shared Platform + CRM domain modules |
| **Alternatives** | Microservices, separate repos per product |
| **Consequences** | Simpler ops; strict module boundaries required to prevent coupling |
| **Revisit** | CRM schema > 500GB or team > 15 backend engineers |

---

## ADR-002: Python/FastAPI Backend

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Context** | Foundation plan specifies Python 3.13 + FastAPI; repo has Express stub |
| **Decision** | Replace Express with Python/FastAPI + uv |
| **Alternatives** | Extend Express/NestJS, Django |
| **Consequences** | Aligns with foundation plan; split language from frontend; need Python skills |
| **Revisit** | Team mandates TypeScript-only backend |

---

## ADR-003: Shared Platform Boundaries

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | Identity, orgs, RBAC, documents, audit, notifications in Platform layer |
| **Rule** | No CRM business logic in Platform; no Platform-specific fields in CRM |

---

## ADR-004: CRM Product Boundaries

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | CRM owns Account, Contact, Lead, Opportunity, Activity, etc. |
| **Rule** | No finance/project/contract fields in CRM tables |

---

## ADR-005: PostgreSQL as Primary Database

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | PostgreSQL 18 with RLS, FTS, pgvector |
| **Alternatives** | MySQL, MongoDB, CockroachDB |
| **Revisit** | Global multi-region write requirements |

---

## ADR-006: SQLAlchemy over Prisma

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Context** | Foundation plan specifies SQLAlchemy; Prisma docs serve as logical model spec |
| **Decision** | SQLAlchemy 2.0 async + Alembic for implementation |
| **Alternatives** | Prisma (requires TypeScript backend) |
| **Revisit** | Backend language change to TypeScript |

---

## ADR-007: Multi-Tenancy — Shared Schema + RLS

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | Shared database, shared schema, `organizationId` + PostgreSQL RLS |
| **Alternatives** | Schema per tenant, DB per tenant |
| **Revisit** | Enterprise customer requires dedicated DB |

---

## ADR-008: Account as Canonical Customer Entity

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Context** | Frontend uses `/accounts` route and `Account` type; copy uses "customer" |
| **Decision** | `Account` is the canonical entity; "Customer" is business language only |
| **Evidence** | `frontend/app/(crm)/accounts/page.tsx` |

---

## ADR-009: Authentication — JWT + Refresh Tokens

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | EdDSA JWT (15 min) + rotating refresh tokens (hashed in DB) |
| **Alternatives** | Session-only, OAuth-only |

---

## ADR-010: Authorization — Hand-Rolled Policy Functions

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | Python policy functions per module/action |
| **Alternatives** | Casbin, Oso, Django Guardian |
| **Revisit** | >50 distinct permission rules |

---

## ADR-011: Product Access Control

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | `ProductEntitlement` table; middleware checks before product APIs |
| **Rule** | CRM access ≠ Books access |

---

## ADR-012: API Style — REST + OpenAPI

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | REST JSON with OpenAPI 3.1; frontend client via orval |
| **Alternatives** | GraphQL, tRPC |

---

## ADR-013: Event Architecture — Outbox + ARQ

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | PostgreSQL outbox table + ARQ worker for MVP |
| **Alternatives** | Kafka, Redis Streams, direct async |
| **Revisit** | >1000 events/sec sustained |

---

## ADR-014: Document Storage — Cloudflare R2

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | R2 via boto3; metadata in Platform Document table |
| **Alternatives** | AWS S3, local storage |

---

## ADR-015: Search — Postgres FTS (MVP)

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | tsvector + GIN + pg_trgm for CRM search |
| **Revisit** | p95 > 200ms or >1M searchable records |

---

## ADR-016: AI Platform — Shared Gateway

| Field | Value |
|-------|-------|
| **Status** | Accepted — implemented |
| **Decision** | `app/platform/ai` owns every model call; products consume it and never a vendor SDK |
| **Rule** | No credential outside the gateway; no AI output that is not a real model response |

**What shipped, and when.** The gateway was built ahead of the Phase 5 schedule
this ADR originally recorded, because S3K CRM Market Insights needed it: a
product feature calling Anthropic directly would have put a vendor SDK and an
API credential inside `app/products/`, which ADR-003 forbids and which no later
refactor recovers cheaply. The deferral was a sequencing assumption, not a
design one, and the design is unchanged.

**Shape.** `AnthropicResearchProvider` implements a `ResearchProvider`
Protocol, so the service layer is testable without a network call and a second
vendor is a new class rather than a change to any caller. `AiGatewayService`
owns provider construction, rate limiting and the audit record, so no feature
has to remember any of the three. `AiPromptService` holds an append-only prompt
library: publishing appends a version, so research pinned to an earlier one
stays reproducible.

**Credentials (revised).** Originally environment-only. Since
`20260831_0300` an organization's administrator can store a credential from
AI Settings → Providers; `platform.ai_provider_credentials` holds it as Fernet
ciphertext, tenant-scoped and RLS-FORCEd, with the encryption key supplied by
the environment and never stored beside the data it protects. Resolution
prefers the organization's own credential and falls back to `ANTHROPIC_API_KEY`,
which remains the bootstrapping path — a deployment still runs AI before anyone
has configured anything. This is the one reversibly-encrypted secret in the
schema; everything else remains hashed, and `app/core/secrets.py` records why
that asymmetry is unavoidable here.

**The AI settings UI is no longer deferred in full.** Prompts and Providers are
implemented against real endpoints. The remaining AI Settings screens (Agents,
Automations, Copilot, Knowledge, Features, Security Analytics) still render
`AiUnavailable` and are honest about having no backend — the mock datasets they
once displayed are retained under `frontend/features/ai/` as specifications,
imported by nothing.

**What has not changed.** An unset credential is a first-class state answered
with `503 ai_not_configured`, and nothing anywhere substitutes canned output for
a model call.

---

## ADR-017: Deployment — TBD (Phase 0)

| Field | Value |
|-------|-------|
| **Status** | Open |
| **Options** | Railway, AWS ECS/Fargate, Fly.io, self-hosted |
| **Decision needed by** | End of Phase 0 |

---

## ADR-018: Observability — OTel + Sentry + Grafana Cloud

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Decision** | structlog JSON + Sentry errors + OTel traces → Grafana Cloud free tier |
| **Revisit** | Move to self-hosted SigNoz on AWS |

---

## ADR Summary Table

| ADR | Topic | Status |
|-----|-------|--------|
| 001 | Modular monolith | Proposed |
| 002 | Python/FastAPI | Proposed |
| 003 | Platform boundaries | Proposed |
| 004 | CRM boundaries | Proposed |
| 005 | PostgreSQL | Proposed |
| 006 | SQLAlchemy | Proposed |
| 007 | RLS multi-tenancy | Proposed |
| 008 | Account naming | Proposed |
| 009 | JWT auth | Proposed |
| 010 | Policy functions | Proposed |
| 011 | Product access | Proposed |
| 012 | REST API | Proposed |
| 013 | Outbox events | Proposed |
| 014 | R2 storage | Proposed |
| 015 | Postgres FTS | Proposed |
| 016 | AI gateway defer | Proposed |
| 017 | Deployment | Open |
| 018 | Observability | Proposed |
