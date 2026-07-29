# Shared Platform — Prisma Schema Design

**Note:** The S3K Technical Foundation Plan specifies **SQLAlchemy 2.0 + Alembic** for implementation. This document defines the **logical data model in Prisma syntax** as a portable specification. SQLAlchemy models should mirror these structures 1:1.

**Implementation:** Single PostgreSQL database, schemas: `platform` and `crm` (logical separation via PostgreSQL schemas).

---

## ID Strategy

- **Primary keys:** UUID v7 (time-sortable)
- **External IDs:** Optional `externalId` + `integrationId` for sync
- **Timestamps:** `createdAt`, `updatedAt` (UTC)
- **Audit:** `createdById`, `updatedById` → `User.id`
- **Soft delete:** `deletedAt` nullable timestamp

---

## PostgreSQL Schema Separation

```sql
CREATE SCHEMA platform;
CREATE SCHEMA crm;
-- RLS policies applied per schema
```

---

## Core Models

### User

```prisma
model User {
  id            String    @id @default(uuid()) @db.Uuid
  email         String    @unique
  emailVerified DateTime?
  passwordHash  String?
  status        UserStatus @default(ACTIVE)
  createdAt     DateTime  @default(now())
  updatedAt     DateTime  @updatedAt
  deletedAt     DateTime?

  profile       UserProfile?
  memberships   OrganizationMembership[]
  sessions      Session[]
  auditLogs     AuditLog[] @relation("AuditActor")

  @@schema("platform")
  @@map("users")
}

enum UserStatus {
  ACTIVE
  DISABLED
  PENDING
  @@schema("platform")
}
```

| Question | Answer |
|----------|--------|
| Shared or Product? | Shared Platform |
| organizationId? | No — user is global; scoped via memberships |
| PII? | Yes — email |
| Scale | 100K users across platform |

### UserProfile

```prisma
model UserProfile {
  id          String  @id @default(uuid()) @db.Uuid
  userId      String  @unique @db.Uuid
  firstName   String
  lastName    String
  avatarUrl   String?
  timezone    String  @default("UTC")
  locale      String  @default("en")
  phone       String?

  user User @relation(fields: [userId], references: [id])

  @@schema("platform")
  @@map("user_profiles")
}
```

### Organization

```prisma
model Organization {
  id          String   @id @default(uuid()) @db.Uuid
  name        String
  slug        String   @unique
  status      OrgStatus @default(ACTIVE)
  settings    Json     @default("{}")
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
  deletedAt   DateTime?

  memberships OrganizationMembership[]
  teams       Team[]
  departments Department[]

  @@schema("platform")
  @@map("organizations")
}

enum OrgStatus {
  ACTIVE
  SUSPENDED
  ARCHIVED
  @@schema("platform")
}
```

### OrganizationMembership

```prisma
model OrganizationMembership {
  id             String           @id @default(uuid()) @db.Uuid
  organizationId String           @db.Uuid
  userId         String           @db.Uuid
  status         MembershipStatus @default(ACTIVE)
  isDefault      Boolean          @default(false)
  joinedAt       DateTime         @default(now())

  organization Organization @relation(fields: [organizationId], references: [id])
  user         User         @relation(fields: [userId], references: [id])
  roles        MembershipRole[]

  @@unique([organizationId, userId])
  @@index([userId])
  @@schema("platform")
  @@map("organization_memberships")
}
```

### Team & Department

```prisma
model Department {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  name           String
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt

  organization Organization @relation(fields: [organizationId], references: [id])
  teams        Team[]

  @@unique([organizationId, name])
  @@index([organizationId])
  @@schema("platform")
}

model Team {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  departmentId   String? @db.Uuid
  name           String
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt

  organization Organization @relation(fields: [organizationId], references: [id])
  department   Department?  @relation(fields: [departmentId], references: [id])
  members      TeamMembership[]

  @@unique([organizationId, name])
  @@index([organizationId])
  @@schema("platform")
}

model TeamMembership {
  id       String @id @default(uuid()) @db.Uuid
  teamId   String @db.Uuid
  userId   String @db.Uuid
  joinedAt DateTime @default(now())

  team Team @relation(fields: [teamId], references: [id])
  user User @relation(fields: [userId], references: [id])

  @@unique([teamId, userId])
  @@schema("platform")
}
```

### Role & Permission

```prisma
model Role {
  id             String  @id @default(uuid()) @db.Uuid
  organizationId String? @db.Uuid  // null = system role template
  productId      String? @db.Uuid
  name           String
  description    String?
  isSystem       Boolean @default(false)
  createdAt      DateTime @default(now())

  permissions RolePermission[]
  assignments MembershipRole[]

  @@unique([organizationId, productId, name])
  @@schema("platform")
}

model Permission {
  id          String @id @default(uuid()) @db.Uuid
  productId   String @db.Uuid
  module      String  // e.g. "leads", "accounts"
  action      PermissionAction
  description String?

  roles RolePermission[]

  @@unique([productId, module, action])
  @@schema("platform")
}

enum PermissionAction {
  VIEW
  CREATE
  EDIT
  DELETE
  EXPORT
  ADMIN
  @@schema("platform")
}

model RolePermission {
  roleId       String @db.Uuid
  permissionId String @db.Uuid
  role         Role       @relation(fields: [roleId], references: [id])
  permission   Permission @relation(fields: [permissionId], references: [id])
  @@id([roleId, permissionId])
  @@schema("platform")
}

model MembershipRole {
  membershipId String @db.Uuid
  roleId       String @db.Uuid
  assignedAt   DateTime @default(now())
  membership   OrganizationMembership @relation(fields: [membershipId], references: [id])
  role         Role @relation(fields: [roleId], references: [id])
  @@id([membershipId, roleId])
  @@schema("platform")
}
```

### Product & ProductAccess

```prisma
model Product {
  id   String @id @default(uuid()) @db.Uuid
  code String @unique  // "s3k-crm", "s3k-books"
  name String
  status ProductStatus @default(ACTIVE)

  entitlements ProductEntitlement[]
  permissions  Permission[]

  @@schema("platform")
}

model ProductEntitlement {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  productId      String @db.Uuid
  status         EntitlementStatus @default(ACTIVE)
  grantedAt      DateTime @default(now())
  expiresAt      DateTime?

  product Product @relation(fields: [productId], references: [id])

  @@unique([organizationId, productId])
  @@schema("platform")
}
```

### Session

```prisma
model Session {
  id               String   @id @default(uuid()) @db.Uuid
  userId           String   @db.Uuid
  refreshTokenHash String
  organizationId   String?  @db.Uuid  // active org context
  ipAddress        String?
  userAgent        String?
  expiresAt        DateTime
  revokedAt        DateTime?
  createdAt        DateTime @default(now())

  user User @relation(fields: [userId], references: [id])

  @@index([userId])
  @@index([refreshTokenHash])
  @@schema("platform")
}
```

### Document & File Storage

```prisma
model Document {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  name           String
  mimeType       String
  sizeBytes      BigInt
  status         DocumentStatus @default(ACTIVE)
  createdById    String @db.Uuid
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
  deletedAt      DateTime?

  versions DocumentVersion[]
  links    DocumentLink[]

  @@index([organizationId, createdAt])
  @@schema("platform")
}

model DocumentVersion {
  id         String @id @default(uuid()) @db.Uuid
  documentId String @db.Uuid
  version    Int
  storageKey String  // R2 object key
  checksum   String?
  createdAt  DateTime @default(now())

  document Document @relation(fields: [documentId], references: [id])

  @@unique([documentId, version])
  @@schema("platform")
}

model DocumentLink {
  id             String @id @default(uuid()) @db.Uuid
  documentId     String @db.Uuid
  organizationId String @db.Uuid
  productCode    String  // "s3k-crm"
  entityType     String  // "account", "lead", "opportunity"
  entityId       String @db.Uuid

  document Document @relation(fields: [documentId], references: [id])

  @@index([organizationId, productCode, entityType, entityId])
  @@index([documentId])
  @@schema("platform")
}
```

**Design note:** Polorphic link via typed `entityType` + `entityId` with application-level validation. No unsafe DB-level polymorphic FK.

### AuditLog

```prisma
model AuditLog {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  actorId        String? @db.Uuid
  action         String
  module         String
  entityType     String?
  entityId       String? @db.Uuid
  ipAddress      String?
  metadata       Json?
  status         AuditStatus
  createdAt      DateTime @default(now())

  actor User? @relation("AuditActor", fields: [actorId], references: [id])

  @@index([organizationId, createdAt])
  @@index([organizationId, module, createdAt])
  @@schema("platform")
}
```

### Notification

```prisma
model Notification {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  userId         String @db.Uuid
  type           String
  title          String
  body           String?
  readAt         DateTime?
  metadata       Json?
  createdAt      DateTime @default(now())

  @@index([userId, readAt, createdAt])
  @@index([organizationId, createdAt])
  @@schema("platform")
}
```

### Integration & Webhook (Phase 4)

```prisma
model Integration {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  provider       String
  status         IntegrationStatus
  config         Json
  createdAt      DateTime @default(now())

  credentials IntegrationCredential[]

  @@index([organizationId])
  @@schema("platform")
}

model Webhook {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  url            String
  events         String[]
  secret         String
  status         WebhookStatus @default(ACTIVE)

  deliveries WebhookDelivery[]

  @@schema("platform")
}
```

### AI Usage (Shared AI Gateway)

```prisma
model AIUsageLog {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  userId         String @db.Uuid
  productCode    String
  model          String
  inputTokens    Int
  outputTokens   Int
  costUsd        Decimal?
  createdAt      DateTime @default(now())

  @@index([organizationId, createdAt])
  @@schema("platform")
}
```

---

## Prisma Separation Strategy Recommendation

| Approach | Recommendation |
|----------|----------------|
| **MVP** | Single database, PostgreSQL schemas (`platform`, `crm`), SQLAlchemy models grouped by module |
| **Prisma multi-file** | Use for documentation only unless team chooses TypeScript backend |
| **Separate databases** | Defer until product extraction or compliance requires |
| **Separate Prisma clients** | Not needed at MVP |

**Revisit trigger:** CRM database exceeds 500GB or independent deployment required.

---

## Entity Classification Matrix (Shared Platform)

| Entity | Owning Product | Shared | Tenant Scoped | Reusable | Cross-Product Ref | API Required | Event Required | Scale |
|--------|---------------|--------|---------------|----------|-------------------|--------------|----------------|-------|
| User | Platform | Yes | No | Yes | Yes (ID only) | Yes | UserCreated | 100K |
| Organization | Platform | Yes | Self | Yes | Yes | Yes | OrgCreated | 10K |
| Membership | Platform | Yes | Yes | Yes | Yes | Yes | MembershipCreated | 500K |
| Role | Platform | Yes | Yes | Yes | No | Yes | RoleAssigned | 50K |
| Permission | Platform | Yes | No | Yes | No | Yes | No | 1K |
| Document | Platform | Yes | Yes | Yes | Via DocumentLink | Yes | DocumentUploaded | Millions |
| AuditLog | Platform | Yes | Yes | Yes | No | Yes (read) | No | Millions |
| Notification | Platform | Yes | Yes | Yes | No | Yes | NotificationCreated | Millions |
| ProductEntitlement | Platform | Yes | Yes | Yes | No | Yes | ProductAccessGranted | 50K |

---

## RLS Policy Pattern

```sql
-- Example: organization-scoped table
ALTER TABLE crm.accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON crm.accounts
  USING (organization_id = current_setting('app.current_org_id')::uuid);
```

Set `app.current_org_id` in FastAPI middleware after JWT + membership validation.
