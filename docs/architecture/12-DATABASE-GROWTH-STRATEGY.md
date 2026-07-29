# Database Growth Strategy

---

## Expected Data Growth

| Entity | 100 Users | 1K Users | 10K Users | 100K Users |
|--------|-----------|----------|-----------|------------|
| Accounts | 5K | 50K | 500K | 5M |
| Contacts | 25K | 250K | 2.5M | 25M |
| Leads | 50K | 500K | 5M | 50M |
| Opportunities | 10K | 100K | 1M | 10M |
| Activities | 500K | 5M | 50M | 500M |
| Audit Logs | 1M | 10M | 100M | 1B |
| Documents | 50K | 500K | 5M | 50M |

Assumptions: ~50 accounts/org, ~5 contacts/account, high activity logging.

---

## Primary Key Strategy

| Decision | UUID v7 (time-sortable) |
|----------|------------------------|
| Why | No coordination needed; sortable; safe for distributed systems |
| When | MVP |
| Alternative trigger | None until proven collision/performance issue |

---

## Index Strategy

### Tenant-Aware Composite Indexes (All CRM Tables)
```sql
CREATE INDEX idx_accounts_org_status ON crm.accounts (organization_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_leads_org_owner ON crm.leads (organization_id, owner_id, status);
CREATE INDEX idx_opportunities_org_stage ON crm.opportunities (organization_id, stage_id);
CREATE INDEX idx_activities_org_entity ON crm.activities (organization_id, related_entity_type, related_entity_id);
CREATE INDEX idx_audit_org_created ON platform.audit_logs (organization_id, created_at DESC);
```

### Partial Indexes
- Active records only: `WHERE deleted_at IS NULL`
- Open opportunities: `WHERE won_at IS NULL AND lost_at IS NULL`

### Full-Text Search
```sql
ALTER TABLE crm.accounts ADD COLUMN search_vector tsvector;
CREATE INDEX idx_accounts_fts ON crm.accounts USING GIN(search_vector);
-- pg_trgm for fuzzy matching
CREATE INDEX idx_accounts_name_trgm ON crm.accounts USING GIN(name gin_trgm_ops);
```

**When:** MVP for search module. **Trigger for dedicated engine:** >1M searchable records or p95 > 200ms.

---

## Partitioning Strategy

| Table | Strategy | Trigger |
|-------|----------|---------|
| audit_logs | Range by month | >10M rows |
| outbox_events | Range by week | >1M rows |
| activities | Range by quarter | >50M rows |
| ai_usage_logs | Range by month | >5M rows |

**MVP:** No partitioning. Monitor table sizes.

---

## Archiving & Retention

| Data | Retention | Archive Strategy |
|------|-----------|-----------------|
| Audit logs | 2 years active, 7 years cold | Move to S3 Parquet |
| Closed opportunities | Indefinite | Soft delete only |
| Converted/lost leads | 3 years active | Archive job |
| Deleted documents | 30 days | Hard delete from R2 |
| Sessions | 30 days | Auto-purge |

---

## Read Replicas

| Stage | Setup |
|-------|-------|
| MVP (100-1K users) | Single primary |
| Medium (1K-10K) | 1 read replica for reports/dashboard |
| Large (10K+) | Dedicated reporting replica |

**Trigger:** Primary CPU > 70% sustained or report queries impact OLTP.

---

## Dashboard Pre-Aggregation

| Stage | Approach |
|-------|----------|
| MVP | Real-time SQL aggregation |
| Medium | Materialized views refreshed hourly |
| Large | Dedicated summary tables updated by ARQ jobs |

```sql
-- Example materialized view (Phase 3+)
CREATE MATERIALIZED VIEW crm.dashboard_pipeline_summary AS
SELECT organization_id, stage_id, COUNT(*), SUM(deal_value)
FROM crm.opportunities WHERE deleted_at IS NULL
GROUP BY organization_id, stage_id;
```

---

## Analytics Architecture

| Stage | Solution |
|-------|----------|
| MVP | SQL queries on primary/replica |
| Growth | Read replica + scheduled exports |
| Scale | Data warehouse (BigQuery/Snowflake) via ETL |

**Not MVP.** Trigger: customer requests custom analytics or >100GB CRM data.

---

## Connection Pooling

| Component | Config |
|-----------|--------|
| FastAPI | asyncpg pool: min=5, max=20 per worker |
| ARQ workers | Separate pool: max=10 |
| MVP scale | PgBouncer in transaction mode when >50 connections |

---

## Backup & Recovery

| Item | Policy |
|------|--------|
| PostgreSQL | Daily full + WAL continuous archiving |
| R2 | Versioning enabled, cross-region replication (enterprise) |
| Recovery target | RPO: 1 hour, RTO: 4 hours |
| Testing | Monthly restore drill |

---

## Multi-Region Roadmap

| Stage | Deployment |
|-------|-----------|
| MVP | Single region (India or US based on customer base) |
| Enterprise | Read replica in customer region |
| Regulated | Dedicated database per region |

**Trigger:** Customer contract requires data residency.

---

## Product Database Separation Triggers

| Trigger | Action |
|---------|--------|
| CRM schema > 500GB | Evaluate CRM schema extraction |
| Independent release cadence needed | Extract CRM to separate service |
| Team > 15 backend engineers | Consider service boundaries |

**MVP:** Single database, logical schema separation (`platform`, `crm`).

---

## Tenant Database Separation Triggers

| Trigger | Action |
|---------|--------|
| Enterprise contract requires dedicated DB | Hybrid tenancy model |
| Noisy neighbor on shared DB | Dedicated instance for large tenant |
| Compliance (HIPAA, etc.) | Dedicated DB + encryption |

**MVP:** Shared database with RLS. Hybrid for enterprise tier.

---

## Cache Strategy

| Data | Cache | TTL |
|------|-------|-----|
| User permissions | Redis | 5 min |
| Dashboard KPIs | Redis | 5 min (large tenants) |
| Org settings | Redis | 15 min |
| Entity detail | No cache (MVP) | — |

Cache keys must include `organizationId`: `crm:accounts:{orgId}:{accountId}`

---

## Scale Stage Summary

| Scale | Users | Key Actions |
|-------|-------|-------------|
| MVP | 100 | Single DB, RLS, basic indexes, no partitioning |
| Medium | 1K-10K | Read replica, materialized views, Redis cache |
| Large | 10K-100K | Partitioning, pre-aggregation, search engine |
| Enterprise | 100K+ | Hybrid tenancy, multi-region, warehouse |
