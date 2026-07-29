# Risks, Open Questions, and Decisions

---

## Risk Register

| ID | Risk | Impact | Probability | Modules | Mitigation | Owner | Phase |
|----|------|--------|-------------|---------|------------|-------|-------|
| R01 | Weak tenant isolation | Critical | Medium | All | RLS + middleware + mandatory testcontainers tests | Backend Lead | Phase 1 |
| R02 | Product boundary leakage | High | Medium | CRM, Platform | ADRs, code review, module import rules | Architect | Phase 0 |
| R03 | CRM becomes system of record for unrelated domains | High | Medium | CRM | Product boundary docs, schema review gate | Architect | Phase 2 |
| R04 | Duplicate user systems | High | Low | Platform | Single User entity, no CRM user table | Backend Lead | Phase 1 |
| R05 | Account/Customer naming ambiguity | Medium | High | CRM, API | ADR-008: Account canonical | Product | Phase 0 |
| R06 | Product-specific fields in shared tables | High | Medium | Platform | Schema review checklist | Architect | All |
| R07 | Direct cross-product DB writes | High | Low | Integration | API/event-only rule | Architect | Phase 4 |
| R08 | Premature microservices | Medium | Medium | Infra | Modular monolith ADR | Architect | Phase 0 |
| R09 | Authorization frontend-only | Critical | **Current state** | All | Backend policy functions Phase 1 | Backend Lead | Phase 1 |
| R10 | Missing product-access controls | Critical | **Current state** | Platform | ProductEntitlement middleware | Backend Lead | Phase 1 |
| R11 | Schema migration failures | High | Medium | Database | Alembic review, staging migrations | Backend Lead | Phase 1 |
| R12 | Large activity table growth | Medium | High | Activities | Partitioning strategy documented | Backend Lead | Phase 2 |
| R13 | Dashboard query performance | Medium | Medium | Dashboard | Aggregation + cache at scale | Backend Lead | Phase 3 |
| R14 | Search permission leakage | High | Medium | Search | Permission filter in search service | Backend Lead | Phase 3 |
| R15 | File storage security | High | Medium | Documents | Pre-signed URLs, permission checks | Backend Lead | Phase 2 |
| R16 | AI data leakage | Critical | Low (deferred) | AI | Gateway with retrieval auth | Architect | Phase 5 |
| R17 | Backend stack drift (Express vs FastAPI) | High | **Current state** | Backend | Replace Express stub Phase 0 | Backend Lead | Phase 0 |
| R18 | Integration event failure | Medium | Medium | Events | Outbox + retry + dead letter | Backend Lead | Phase 4 |
| R19 | Event duplication | Medium | Medium | Events | Idempotency keys | Backend Lead | Phase 4 |
| R20 | Uncontrolled custom fields | Medium | Medium | CRM | CRMCustomField with validation | Backend Lead | Phase 3 |
| R21 | Inadequate audit logging | High | Medium | Platform | Audit service from Phase 1 | Backend Lead | Phase 1 |
| R22 | Frontend type fragmentation | Medium | **Current state** | Frontend | Extract shared types Phase 0 | Frontend Lead | Phase 0 |
| R23 | Pipeline stage inconsistency | Medium | **Current state** | CRM | Seed Pipeline/PipelineStage tables | Backend Lead | Phase 2 |
| R24 | Detail pages ignore URL id | Medium | **Current state** | Frontend | Wire to API Phase 3 | Frontend Lead | Phase 3 |
| R25 | Vendor lock-in (R2, Grafana) | Low | Medium | Infra | S3-compatible, OTel standard | DevOps | Ongoing |

---

## Open Questions

### Product

| # | Question | Why It Matters | Default Assumption | Impact | Owner | Resolve By |
|---|----------|---------------|-------------------|--------|-------|------------|
| P01 | Single org or multi-org per user at launch? | Affects membership UX | Multi-org with switching | Auth + UI complexity | Product | Phase 1 |
| P02 | Is "Account" the external API term or expose "Customer"? | API naming | Account internally, Customer alias in docs | API design | Product | Phase 0 |
| P03 | Are reports required for MVP? | No frontend route exists | Defer to Phase 3 | Scope | Product | Phase 2 |
| P04 | India market first or global? | Affects SMS (MSG91), data residency | India-first | Infra region | Product | Phase 0 |

### CRM

| # | Question | Why It Matters | Default Assumption | Owner | Resolve By |
|---|----------|---------------|-------------------|-------|------------|
| C01 | Should Meeting be Activity subtype or separate? | Schema design | Activity + Meeting extension | Architect | Phase 2 |
| C02 | Lead conversion: always create new Account? | Business logic | Create or link existing Account | Product | Phase 2 |
| C03 | Duplicate detection: block or warn? | UX + data quality | Warn, allow override | Product | Phase 2 |
| C04 | Custom fields in MVP? | Scope | Defer to Phase 3 | Product | Phase 2 |

### Shared Platform

| # | Question | Why It Matters | Default Assumption | Owner | Resolve By |
|---|----------|---------------|-------------------|-------|------------|
| S01 | Self-registration or admin-provisioned users? | Auth flow | Admin-provisioned for MVP | Product | Phase 1 |
| S02 | Default roles at org creation? | RBAC seed | Admin, Sales Manager, Sales Rep | Product | Phase 1 |
| S03 | MFA required at launch? | Security | Optional, admin-enforced later | Security | Phase 1 |

### Database

| # | Question | Why It Matters | Default Assumption | Owner | Resolve By |
|---|----------|---------------|-------------------|-------|------------|
| D01 | PostgreSQL 18 or 17? | Foundation plan says 18 (beta) | PG 17 stable, upgrade to 18 when GA | DevOps | Phase 0 |
| D02 | UUID v4 or v7? | Index performance | UUID v7 | Architect | Phase 0 |

### Security

| # | Question | Why It Matters | Default Assumption | Owner | Resolve By |
|---|----------|---------------|-------------------|-------|------------|
| SEC01 | Cookie vs localStorage for tokens? | XSS risk | httpOnly cookie for refresh | Security | Phase 1 |
| SEC02 | Password complexity requirements? | Admin security page shows policy | Min 12 chars, mixed case, number | Security | Phase 1 |

### Infrastructure

| # | Question | Why It Matters | Default Assumption | Owner | Resolve By |
|---|----------|---------------|-------------------|-------|------------|
| I01 | Deployment platform? | CI/CD setup | Railway for MVP | DevOps | Phase 0 |
| I02 | Managed Postgres provider? | Ops | Neon or RDS | DevOps | Phase 0 |

### AI

| # | Question | Why It Matters | Default Assumption | Owner | Resolve By |
|---|----------|---------------|-------------------|-------|------------|
| A01 | AI features in CRM MVP? | Frontend has AI panels | Store aiScore field; compute externally later | Product | Phase 2 |
| A02 | Which AI providers at launch? | AI settings UI lists 4 | Defer provider integration to Phase 5 | Product | Phase 4 |

### Future Products

| # | Question | Why It Matters | Default Assumption | Owner | Resolve By |
|---|----------|---------------|-------------------|-------|------------|
| F01 | Which product after CRM? | Roadmap priority | Projects or Books based on customer demand | Product | Phase 4 |
| F02 | Event bus technology at scale? | Integration architecture | Outbox → Redis Streams → Kafka | Architect | Phase 4 |

---

## Decisions Required Before Coding

| Priority | Decision | Recommended Default |
|----------|----------|-------------------|
| **P0** | Confirm Python/FastAPI backend (retire Express) | Yes — per foundation plan |
| **P0** | Confirm Account as canonical entity (not Customer table) | Yes |
| **P0** | Confirm RLS multi-tenancy model | Yes |
| **P1** | Multi-org per user at launch | Yes |
| **P1** | Deployment platform | Railway (MVP) |
| **P2** | Reports in MVP scope | No — Phase 3 |
| **P2** | AI backend in MVP scope | No — store fields only |

---

## Completion Checklist

- [x] Full repository reviewed
- [x] Frontend routes inventoried (31 CRM pages)
- [x] Mock/static data identified (all pages)
- [x] Existing APIs identified (none — Express `/health` only)
- [x] Prisma models reviewed (none exist — designed in docs)
- [x] Technical Foundation Plan reviewed (Python/FastAPI/SQLAlchemy)
- [x] Product vision applied (Platform + CRM + future products)
- [x] Platform, CRM, future boundaries defined
- [x] Only CRM + Platform planned for implementation
- [x] Shared and product-owned entities identified
- [x] Prisma logical schemas designed
- [x] Account/Customer naming resolved (Account)
- [x] Tenant isolation documented
- [x] No production code changed
- [x] No migrations executed
