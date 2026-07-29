# Cross-Product Entity Relationship Diagram

**Purpose:** Visualize ownership, direct DB relationships, API references, and event-based links across S3K products.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| Solid line | Direct FK within same database |
| Dashed line | API reference (stable UUID, no FK) |
| Dotted line | Event-driven projection |
| 🟦 | Shared Platform ownership |
| 🟩 | S3K CRM ownership |
| 🟨 | Future product ownership |

---

## Platform + CRM Core ERD

```mermaid
erDiagram
  Organization ||--o{ OrganizationMembership : has
  User ||--o{ OrganizationMembership : belongs
  Organization ||--o{ Team : has
  Organization ||--o{ Department : has
  User ||--o| UserProfile : has
  Organization ||--o{ ProductEntitlement : grants
  Product ||--o{ ProductEntitlement : enables
  Role ||--o{ RolePermission : has
  Permission ||--o{ RolePermission : defines
  OrganizationMembership ||--o{ MembershipRole : assigned

  Organization ||--o{ Account : tenants
  Account ||--o{ Contact : employs
  Account ||--o{ Opportunity : tracks
  LeadSource ||--o{ Lead : sources
  Lead ||--o| QualificationRecord : assesses
  Campaign ||--o{ Lead : attributes
  Pipeline ||--o{ PipelineStage : contains
  PipelineStage ||--o{ Opportunity : stages
  Opportunity ||--o{ OpportunityStageHistory : logs
  Activity ||--o| Meeting : extends
  Account ||--o{ Activity : related
  Contact ||--o{ Activity : related
  Lead ||--o{ Activity : related
  Opportunity ||--o{ Activity : related

  Document ||--o{ DocumentLink : links
  User ||--o{ AuditLog : performs
  User ||--o{ Notification : receives

  Organization {
    uuid id PK
    string name
    string slug
  }
  User {
    uuid id PK
    string email
  }
  Account {
    uuid id PK
    uuid organizationId FK
    string name
    enum status
  }
  Contact {
    uuid id PK
    uuid accountId FK
    uuid organizationId FK
  }
  Lead {
    uuid id PK
    uuid organizationId FK
    enum status
  }
  Opportunity {
    uuid id PK
    uuid accountId FK
    uuid stageId FK
  }
  Document {
    uuid id PK
    uuid organizationId FK
  }
  DocumentLink {
    uuid id PK
    string productCode
    string entityType
    uuid entityId
  }
```

---

## Cross-Product Reference Diagram

```mermaid
flowchart TB
  subgraph Platform["🟦 Shared Platform"]
    Org[Organization]
    User[User]
    Doc[Document]
    Audit[AuditLog]
    Notify[Notification]
    AI[AI Gateway]
  end

  subgraph CRM["🟩 S3K CRM"]
    Account[Account]
    Contact[Contact]
    Lead[Lead]
    Opp[Opportunity]
  end

  subgraph Books["🟨 S3K Books (Future)"]
    Invoice[Invoice]
    Payment[Payment]
  end

  subgraph Projects["🟨 S3K Projects (Future)"]
    Project[Project]
    Milestone[Milestone]
  end

  subgraph Contracts["🟨 S3K Contracts (Future)"]
    Contract[Contract]
  end

  subgraph Support["🟨 S3K Support (Future)"]
    Ticket[Ticket]
  end

  Org --> Account
  User --> Account
  Account --> Contact
  Account --> Opp

  Account -.->|API ref| Invoice
  Account -.->|API ref| Project
  Account -.->|API ref| Contract
  Contact -.->|API ref| Ticket
  Opp -.->|API ref| Project
  Opp -.->|event: won| Project

  Doc -->|DocumentLink| Account
  Doc -->|DocumentLink| Contract
  AI -->|authorized API| CRM
  AI -->|authorized API| Support
```

---

## Product Access Relationships

```mermaid
flowchart LR
  User --> Membership[OrganizationMembership]
  Membership --> Role[Role]
  Role --> Permission[Permission]
  Org[Organization] --> Entitlement[ProductEntitlement]
  Entitlement --> Product[Product: s3k-crm]
  Permission --> Module[CRM Module Access]
  Module --> API[CRM API Endpoints]
```

---

## Document Linking Model

```mermaid
flowchart TB
  Upload[Pre-signed Upload URL] --> R2[Cloudflare R2]
  R2 --> DocVersion[DocumentVersion]
  DocVersion --> Document
  Document --> Link[DocumentLink]
  Link --> |entityType=account| Account
  Link --> |entityType=lead| Lead
  Link --> |entityType=opportunity| Opportunity
  Link --> |entityType=contract| ContractFuture[Future Contract]
```

**Security:** DocumentLink creation requires product permission check on target entity.

---

## Tenant Ownership Flow

```mermaid
sequenceDiagram
  participant Req as HTTP Request
  participant Auth as Auth Middleware
  participant Ctx as Tenant Context
  participant RLS as PostgreSQL RLS
  participant Data as CRM Data

  Req->>Auth: JWT + X-Organization-Id
  Auth->>Auth: Validate membership
  Auth->>Ctx: Set organizationId, userId
  Ctx->>RLS: SET app.current_org_id
  RLS->>Data: Filtered query
  Data-->>Req: Tenant-scoped results
```

---

## Relationship Type Summary

| From | To | Type | Access Method |
|------|-----|------|---------------|
| Organization | Account | Direct FK | Same DB |
| Account | Contact | Direct FK | Same DB |
| Account | Opportunity | Direct FK | Same DB |
| CRM Account | Books Invoice | API ref | `accountId` UUID validation |
| CRM Opportunity | Projects Project | API ref + event | `crm.opportunity.won` |
| CRM Account | Contracts Contract | API ref | REST lookup |
| Platform Document | CRM Account | DocumentLink | Platform service |
| Platform User | CRM Lead.owner | Direct FK | Same DB |
| S3K AI | CRM entities | API only | Never direct DB |
