# CRM — Prisma Schema Design

**Note:** Logical model in Prisma syntax. Implement as SQLAlchemy models in `crm` PostgreSQL schema.

**Frontend evidence:** Types extracted from `frontend/app/(crm)/*/page.tsx`.

---

## Naming Decisions

| Question | Decision | Evidence |
|----------|----------|----------|
| Customer vs Account? | **Account** only | Routes: `/accounts`, type in `accounts/page.tsx` |
| Contact belongs to? | Account via `accountId` FK | `contacts/page.tsx` — field currently string |
| Meeting vs Activity? | Activity base + Meeting extension | Both modules in frontend |
| Task vs Activity? | Separate Task entity | Dashboard `TaskCard` component |
| Qualification entity? | `QualificationRecord` linked to Lead | `qualification/page.tsx` — separate from Lead list |

---

## Account (formerly "Customer" in business language)

```prisma
model Account {
  id             String        @id @default(uuid()) @db.Uuid
  organizationId String        @db.Uuid
  name           String
  industry       String?
  website        String?
  companySize    String?
  annualRevenue  Decimal?
  status         AccountStatus @default(ACTIVE)
  ownerId        String?       @db.Uuid  // User.id
  primaryContactId String?       @db.Uuid
  healthScore    Int?
  source         String?
  description    String?
  // Address
  country        String?
  state          String?
  city           String?
  postalCode     String?
  addressLine1   String?
  externalId     String?
  integrationId  String?       @db.Uuid
  createdById    String        @db.Uuid
  updatedById    String?       @db.Uuid
  createdAt      DateTime      @default(now())
  updatedAt      DateTime      @updatedAt
  deletedAt      DateTime?

  contacts      Contact[]
  opportunities Opportunity[]
  activities    Activity[]

  @@unique([organizationId, name])  // soft — allow dupes with warning
  @@index([organizationId, status])
  @@index([organizationId, ownerId])
  @@index([organizationId, deletedAt])
  @@schema("crm")
  @@map("accounts")
}

enum AccountStatus {
  ACTIVE
  ONBOARDING
  AT_RISK
  CHURNED
  @@schema("crm")
}
```

**Frontend mapping:** `accounts/page.tsx` — statuses: Active, Churned, Onboarding, At Risk → enum above.

---

## Contact

```prisma
model Contact {
  id             String        @id @default(uuid()) @db.Uuid
  organizationId String        @db.Uuid
  accountId      String?       @db.Uuid
  firstName      String
  lastName       String
  email          String?
  phone          String?
  mobile         String?
  jobTitle       String?
  department     String?
  ownerId        String?       @db.Uuid
  reportingManagerId String?   @db.Uuid
  status         ContactStatus @default(ACTIVE)
  aiScore        Int?
  preferredCommunication String?
  linkedInUrl    String?
  notes          String?
  // Address fields
  country        String?
  state          String?
  city           String?
  postalCode     String?
  addressLine1   String?
  createdById    String        @db.Uuid
  updatedById    String?       @db.Uuid
  createdAt      DateTime      @default(now())
  updatedAt      DateTime      @updatedAt
  deletedAt      DateTime?

  account Account? @relation(fields: [accountId], references: [id])

  @@index([organizationId, accountId])
  @@index([organizationId, email])
  @@index([organizationId, ownerId])
  @@schema("crm")
  @@map("contacts")
}

enum ContactStatus {
  ACTIVE
  INACTIVE
  @@schema("crm")
}
```

---

## LeadSource

```prisma
model LeadSource {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  name           String
  category       String?
  description    String?
  status         LeadSourceStatus @default(ACTIVE)
  createdById    String @db.Uuid
  updatedById    String? @db.Uuid
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
  deletedAt      DateTime?

  leads Lead[]

  @@unique([organizationId, name])
  @@index([organizationId, status])
  @@schema("crm")
}

enum LeadSourceStatus {
  ACTIVE
  INACTIVE
  @@schema("crm")
}
```

**Frontend:** `lead-sources/page.tsx` — 10 mock sources, categories as free text.

---

## Lead

```prisma
model Lead {
  id               String     @id @default(uuid()) @db.Uuid
  organizationId   String     @db.Uuid
  firstName        String
  lastName         String
  company          String?     // pre-conversion company name
  email            String?
  phone            String?
  leadSourceId     String?    @db.Uuid
  ownerId          String?    @db.Uuid
  status           LeadStatus @default(NEW)
  aiScore          Int?
  priority         Priority?
  expectedDealSize Decimal?
  industry         String?
  website          String?
  companySize      String?
  notes            String?
  convertedAt      DateTime?
  convertedAccountId String?  @db.Uuid
  convertedContactId String?  @db.Uuid
  campaignId       String?  @db.Uuid
  createdById      String    @db.Uuid
  updatedById      String?   @db.Uuid
  createdAt        DateTime  @default(now())
  updatedAt        DateTime  @updatedAt
  deletedAt        DateTime?

  leadSource     LeadSource? @relation(fields: [leadSourceId], references: [id])
  qualification  QualificationRecord?
  campaign       Campaign?   @relation(fields: [campaignId], references: [id])

  @@index([organizationId, status])
  @@index([organizationId, ownerId])
  @@index([organizationId, email])
  @@index([organizationId, createdAt])
  @@schema("crm")
}

enum LeadStatus {
  NEW
  CONTACTED
  QUALIFIED
  PROPOSAL_SENT
  NEGOTIATION
  CONVERTED
  LOST
  @@schema("crm")
}

enum Priority {
  HIGH
  MEDIUM
  LOW
  @@schema("crm")
}
```

**Frontend mapping:** `leads/page.tsx` — LeadStatus values mapped to SCREAMING_SNAKE enum.

---

## QualificationRecord

```prisma
model QualificationRecord {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  leadId         String @unique @db.Uuid
  framework      QualificationFramework @default(BANT)
  status         QualificationStatus @default(UNQUALIFIED)
  budget         String?
  authority      String?
  need           String?
  timeline       String?
  aiScore        Int?
  recommendation String?
  ownerId        String? @db.Uuid
  priority       Priority?
  checklist      Json?   // framework-specific criteria
  createdById    String @db.Uuid
  updatedById    String? @db.Uuid
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt

  lead Lead @relation(fields: [leadId], references: [id])

  @@index([organizationId, status])
  @@index([organizationId, priority])
  @@schema("crm")
}

enum QualificationFramework {
  BANT
  MEDDICC
  CHAMP
  @@schema("crm")
}

enum QualificationStatus {
  UNQUALIFIED
  IN_REVIEW
  QUALIFIED
  DISQUALIFIED
  @@schema("crm")
}
```

---

## Campaign

```prisma
model Campaign {
  id                    String @id @default(uuid()) @db.Uuid
  organizationId        String @db.Uuid
  name                  String
  type                  CampaignType
  status                CampaignStatus @default(PLANNING)
  ownerId               String? @db.Uuid
  startDate             DateTime?
  endDate               DateTime?
  budget                Decimal?
  expectedRevenue       Decimal?
  targetAudience        String?
  leadSourceId          String? @db.Uuid
  products              String?
  notes                 String?
  // Computed/cached metrics (updated by jobs)
  leadsGenerated        Int @default(0)
  opportunitiesGenerated Int @default(0)
  conversionRate        Decimal?
  roi                   Decimal?
  createdById           String @db.Uuid
  updatedById           String? @db.Uuid
  createdAt             DateTime @default(now())
  updatedAt             DateTime @updatedAt
  deletedAt             DateTime?

  leads   Lead[]
  members CampaignMember[]

  @@index([organizationId, status])
  @@schema("crm")
}

model CampaignMember {
  id         String @id @default(uuid()) @db.Uuid
  campaignId String @db.Uuid
  entityType CampaignMemberType  // LEAD | CONTACT
  entityId   String @db.Uuid
  addedAt    DateTime @default(now())

  campaign Campaign @relation(fields: [campaignId], references: [id])

  @@unique([campaignId, entityType, entityId])
  @@schema("crm")
}

enum CampaignType {
  EMAIL
  WEBINAR
  SOCIAL_MEDIA
  EVENT
  ADVERTISEMENT
  @@schema("crm")
}

enum CampaignStatus {
  PLANNING
  ACTIVE
  PAUSED
  COMPLETED
  CANCELLED
  @@schema("crm")
}
```

---

## Opportunity & Pipeline

```prisma
model Pipeline {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  name           String @default("Default")
  isDefault      Boolean @default(true)

  stages PipelineStage[]

  @@unique([organizationId, name])
  @@schema("crm")
}

model PipelineStage {
  id          String @id @default(uuid()) @db.Uuid
  pipelineId  String @db.Uuid
  name        String
  sortOrder   Int
  probability Int    @default(0)  // default win probability
  isClosed    Boolean @default(false)
  isWon       Boolean @default(false)

  pipeline      Pipeline @relation(fields: [pipelineId], references: [id])
  opportunities Opportunity[]

  @@unique([pipelineId, name])
  @@index([pipelineId, sortOrder])
  @@schema("crm")
}

model Opportunity {
  id               String @id @default(uuid()) @db.Uuid
  organizationId   String @db.Uuid
  name             String
  accountId        String @db.Uuid
  primaryContactId String? @db.Uuid
  ownerId          String? @db.Uuid
  stageId          String @db.Uuid
  dealValue        Decimal?
  currency         String @default("USD")
  winProbability   Int?
  expectedCloseDate DateTime?
  healthScore      Int?
  forecastCategory String?
  competitor       String?
  leadSourceId     String? @db.Uuid
  products         String?
  notes            String?
  wonAt            DateTime?
  lostAt           DateTime?
  lossReason       String?
  winReason        String?
  createdById      String @db.Uuid
  updatedById      String? @db.Uuid
  createdAt        DateTime @default(now())
  updatedAt        DateTime @updatedAt
  deletedAt        DateTime?

  account Account @relation(fields: [accountId], references: [id])
  stage   PipelineStage @relation(fields: [stageId], references: [id])
  stageHistory OpportunityStageHistory[]

  @@index([organizationId, stageId])
  @@index([organizationId, accountId])
  @@index([organizationId, ownerId])
  @@index([organizationId, expectedCloseDate])
  @@schema("crm")
}

model OpportunityStageHistory {
  id            String @id @default(uuid()) @db.Uuid
  opportunityId String @db.Uuid
  fromStageId   String? @db.Uuid
  toStageId     String @db.Uuid
  changedById   String @db.Uuid
  changedAt     DateTime @default(now())

  opportunity Opportunity @relation(fields: [opportunityId], references: [id])

  @@index([opportunityId, changedAt])
  @@schema("crm")
}
```

**Default pipeline stages (seed):** Qualification, Discovery, Proposal, Negotiation, Contract Review, Closed Won, Closed Lost — matches `opportunities/page.tsx`.

---

## Activity, Meeting, Task, Note

```prisma
model Activity {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  type           ActivityType
  subject        String
  description    String?
  status         ActivityStatus @default(PLANNED)
  dueDate        DateTime?
  completedAt    DateTime?
  outcome        String?
  ownerId        String? @db.Uuid
  // Polymorphic relation (app-validated)
  relatedEntityType CrmEntityType?
  relatedEntityId   String? @db.Uuid
  createdById    String @db.Uuid
  updatedById    String? @db.Uuid
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
  deletedAt      DateTime?

  meeting Meeting?

  @@index([organizationId, type, status])
  @@index([organizationId, relatedEntityType, relatedEntityId])
  @@index([organizationId, dueDate])
  @@schema("crm")
}

model Meeting {
  id                  String @id @default(uuid()) @db.Uuid
  activityId          String @unique @db.Uuid
  meetingType         MeetingType
  startTime           DateTime
  endTime             DateTime?
  location            String?
  meetingLink         String?
  agenda              String?
  reminderMinutes     Int?
  internalParticipantIds String[]  // User IDs

  activity Activity @relation(fields: [activityId], references: [id])

  @@schema("crm")
}

model Task {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  title          String
  description    String?
  status         TaskStatus @default(PENDING)
  priority       Priority @default(MEDIUM)
  dueDate        DateTime?
  completedAt    DateTime?
  ownerId        String? @db.Uuid
  assignedToId   String? @db.Uuid
  relatedEntityType CrmEntityType?
  relatedEntityId   String? @db.Uuid
  createdById    String @db.Uuid
  updatedById    String? @db.Uuid
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
  deletedAt      DateTime?

  @@index([organizationId, assignedToId, status])
  @@index([organizationId, dueDate])
  @@schema("crm")
}

model Note {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  content        String
  visibility     NoteVisibility @default(TEAM)
  authorId       String @db.Uuid
  relatedEntityType CrmEntityType
  relatedEntityId   String @db.Uuid
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt
  deletedAt      DateTime?

  @@index([organizationId, relatedEntityType, relatedEntityId])
  @@schema("crm")
}

enum ActivityType {
  CALL
  EMAIL
  MEETING
  OTHER
  @@schema("crm")
}

enum CrmEntityType {
  ACCOUNT
  CONTACT
  LEAD
  OPPORTUNITY
  CAMPAIGN
  @@schema("crm")
}
```

---

## Tags & Custom Fields

```prisma
model CRMTag {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  name           String
  color          String?

  entityTags CRMEntityTag[]

  @@unique([organizationId, name])
  @@schema("crm")
}

model CRMEntityTag {
  id         String @id @default(uuid()) @db.Uuid
  tagId      String @db.Uuid
  entityType CrmEntityType
  entityId   String @db.Uuid

  tag CRMTag @relation(fields: [tagId], references: [id])

  @@unique([tagId, entityType, entityId])
  @@schema("crm")
}

model CRMCustomField {
  id             String @id @default(uuid()) @db.Uuid
  organizationId String @db.Uuid
  entityType     CrmEntityType
  name           String
  fieldType      CustomFieldType
  options        Json?
  isRequired     Boolean @default(false)

  values CRMCustomFieldValue[]

  @@unique([organizationId, entityType, name])
  @@schema("crm")
}

model CRMCustomFieldValue {
  id           String @id @default(uuid()) @db.Uuid
  customFieldId String @db.Uuid
  entityId     String @db.Uuid
  value        Json

  customField CRMCustomField @relation(fields: [customFieldId], references: [id])

  @@unique([customFieldId, entityId])
  @@schema("crm")
}
```

---

## Entity Classification Matrix (CRM)

| Entity | Owner | Shared | Tenant | Cross-Product | API | Event | Scale |
|--------|-------|--------|--------|---------------|-----|-------|-------|
| Account | CRM | No* | Yes | Books/Projects read | Yes | AccountCreated | 1M |
| Contact | CRM | No | Yes | Books/Support read | Yes | ContactCreated | 5M |
| Lead | CRM | No | Yes | No | Yes | LeadCreated | 10M |
| LeadSource | CRM | No | Yes | No | Yes | No | 10K |
| Campaign | CRM | No | Yes | No | Yes | No | 100K |
| QualificationRecord | CRM | No | Yes | No | Yes | LeadQualified | 5M |
| Opportunity | CRM | No | Yes | Projects ref | Yes | OppStageChanged | 5M |
| Activity | CRM | No | Yes | No | Yes | ActivityCreated | 50M+ |
| Task | CRM | No | Yes | No | Yes | TaskCompleted | 10M |
| Note | CRM | No | Yes | No | Yes | NoteCreated | 20M |
| Pipeline/Stage | CRM | No | Yes | No | Yes | No | 1K |

*Account is CRM-owned but consumed by future products via API (not shared ownership).

---

## Document Linkage

Attachments use Platform `Document` + `DocumentLink`:

```
DocumentLink {
  productCode: "s3k-crm"
  entityType: "account" | "lead" | "opportunity" | ...
  entityId: <uuid>
}
```

No file bytes in CRM tables.
