# S3K CRM — Zoho CRM Reference Analysis & Improvement Blueprint

> **Purpose.** Research Zoho CRM as a *reference implementation* of a mature, general-purpose
> CRM, then derive a practical improvement blueprint for S3K CRM. Zoho is a reference, not a
> template — every recommendation in later phases is tagged as
> `[Zoho does this]`, `[CRM best practice]`, `[S3K-specific adaptation]`, or
> `[Intentionally not adopted]`.
>
> **Guiding question throughout:** *if the user enters this information once, how can the CRM
> use it everywhere else so they never re-enter it?*
>
> **Status:** Research complete (six phases); Stages 0–4 implemented, 5–6 partial. See
> "Phase 5/6 corrections" and "Implementation status" at the end.

---

## Document conventions

| Marker | Meaning |
|---|---|
| **Zoho:** | Documented Zoho CRM behaviour, sourced from official Zoho docs |
| **Not confirmed** | Could not be verified in official Zoho documentation; treat as unverified |
| `[tag]` | Recommendation tag (used from Phase 5 onward) |

**A correction to the project brief.** The brief describes this repo as
"Node.js, TypeScript, Prisma, PostgreSQL." That is only half right. The *architecture
documents* (`docs/architecture/04-SHARED-PRISMA-SCHEMA.md`,
`docs/architecture/05-CRM-PRISMA-SCHEMA.md`) were written against Prisma, but the
**implemented backend is Python**: FastAPI + SQLAlchemy 2.0 (async) + Alembic on PostgreSQL
(`backend/pyproject.toml`, `backend/migrations/`). There is no `schema.prisma` anywhere in
the tree. The frontend is Next.js/TypeScript. Phase 4 analyses the real stack; this drift
between the planned and the implemented data layer is itself a finding.

---

# Phase 1 — Zoho CRM module research

Zoho CRM's standard module set, as published by Zoho:
Leads, Accounts, Contacts, Deals, Campaigns, Forecasts, Cases, Solutions, Products,
Price Books, Quotes, Sales Orders, Purchase Orders, Invoices, Vendors, Tasks, Meetings,
Calls, Reports, Dashboards, Documents.

Zoho groups these into functional clusters, which is the useful mental model:

| Cluster | Modules | Role in the system |
|---|---|---|
| **Sales Force Automation** | Leads, Accounts, Contacts, Deals | The core entity graph — *who*, and *how much* |
| **Activity Management** | Tasks, Calls, Meetings, Notes | The interaction record — *what happened* |
| **Inventory / Order Management** | Products, Price Books, Quotes, Sales Orders, Invoices, Purchase Orders, Vendors | The commercial paper trail — *what was sold, at what price* |
| **Marketing & Support** | Campaigns, Cases, Solutions | Demand generation and post-sale service |
| **Security & Org** | Users, Roles, Profiles, Groups, Territories | *Who may see and do what* |

---

## 1.1 Summary table — mandatory fields at a glance

This is the single most transferable artefact from Phase 1: Zoho's opinion, refined over
two decades, about the **minimum viable record** for each module. Everything else is optional.

| Module | Mandatory fields (Zoho) | Effective record identity |
|---|---|---|
| **Leads** | Last Name, Company | Person + org, pre-qualification |
| **Accounts** | Account Name | Company |
| **Contacts** | Last Name | Person |
| **Deals** | Deal Name, Account Name, Closing Date, Stage | Revenue event tied to a company |
| **Tasks** | Subject | To-do |
| **Meetings** | Subject, Start Date Time, End Date Time | Scheduled interaction |
| **Calls** | Subject, Call Type, Call Start Time, Call Duration | Logged interaction |
| **Campaigns** | Campaign Name | Marketing spend container |
| **Cases** | Subject, Status, Case Origin | Support ticket |
| **Solutions** | Solution Title, Question, Answer | KB article |
| **Products** | Product Name | Sellable item |
| **Price Books** | Price Book Name | Pricing policy |
| **Quotes** | Subject, Account Name, Product Name, Quantity, List Price | Priced proposal |
| **Sales Orders** | Subject, Account Name, Product Name, Quantity, List Price | Confirmed order |
| **Invoices** | Subject, Account Name, Product Name, Quantity, List Price, Assigned To | Bill |
| **Purchase Orders** | Subject, Vendor Name, Product Name, Quantity, List Price, Assigned To | Procurement |
| **Vendors** | Vendor Name | Supplier |
| **Forecasts** | Year, Quarter | Target period |

Three observations worth carrying into the S3K design:

1. **The mandatory set is brutally small.** Most modules require one or two fields. Zoho
   pushes richness into *optional* fields and lets automation and enrichment fill them in
   later. The cost of creating a record is deliberately near-zero, because a record that
   never gets created is worth less than a thin one.
2. **Deals are the exception** — four mandatory fields, because a deal without a time horizon
   (Closing Date) and a position (Stage) cannot participate in a pipeline or a forecast. Zoho
   enforces exactly what downstream reporting needs, and nothing more.
3. **Every inventory document requires the same five fields.** Quotes, Sales Orders, Invoices
   and Purchase Orders share one shape: header (subject + party) plus line items (product,
   quantity, price). That uniformity is what makes one-click conversion between them possible.
   It is a data-model decision, not a UI decision.

---

## 1.2 Sales Force Automation cluster

### Leads

**What it is.** An unqualified prospect: a person, plus the company they belong to, who has
not yet been validated as worth pursuing. Zoho's Leads module is a **staging area**, kept
deliberately separate from the "real" customer database.

**Why it exists.** To stop unvalidated, duplicate, low-quality inbound data from polluting
Accounts and Contacts. Marketing captures volume; sales qualifies it; only qualified records
graduate. Without this separation, every trade-show badge scan becomes a permanent Account.

**Fields.**
- *Required:* Last Name, Company.
- *Optional (standard):* Lead Owner, Salutation, First Name, Title, Lead Source, Industry,
  Annual Revenue, Phone, Mobile, Fax, Email, Secondary Email, Skype ID, Website, Lead Status,
  Rating, No. of Employees, Email Opt-out, Street/City/State/Zip/Country, Description
  (32,000 chars).
- *System:* Created By, Modified By, Lead Owner (defaults to creator).

Field-length discipline is explicit: First Name 40 chars, Last Name 80, Company 100,
Title 100, Email 100, Website 120, phone fields 30, Annual Revenue 16 digits.

**Creation & import.** Manual form; Quick Create; Clone; CSV/XLSX import; **Web-to-Lead**
forms (auto-capture from a website); API. Zoho supports web forms for Leads, Contacts, Cases
and custom modules only.

**Validation behaviour.**
- Duplicate check runs on **unique fields** — maximum **two unique fields per module**; Email
  is the canonical one for Leads. Manual creation of a duplicate raises a *duplication alert*;
  a single match offers to view the matching record, multiple matches suggest a merge.
- Web-to-Lead submissions that hit a duplicate are **automatically routed for approval**, even
  when lead approval is otherwise disabled.
- API: `insertRecord` refuses duplicates; `updateRecord` blocks an email change that collides;
  `convertLead` fails on duplicate email.
- Duplicate checking is **not** applied during Sheet View editing, data migration, Recycle Bin
  restore, or external contact sync.

**What happens after creation.** The lead is owned (by default by whoever created it), worked
via activities, scored/rated, and eventually **converted** — the single most important state
transition in the product. Conversion is **irreversible**: "A lead cannot be reverted once
converted to contact or account."

**Who consumes lead data.** Contacts, Accounts and Deals (via conversion mapping); Campaigns
(leads are campaign members); Tasks/Calls/Meetings/Notes (attach to leads); reports and
lead-source analytics.

---

### Accounts

**What it is.** The company/organisation record — the customer entity that owns relationships,
deals and money.

**Why it exists.** It is the **aggregation point**. Multiple people, multiple deals, multiple
invoices and multiple support cases all roll up to one company, producing the "how is this
customer doing overall" view that a contact-only model cannot.

**Fields.**
- *Required:* Account Name.
- *Optional (standard):* Account Owner, Website, Ticker Symbol, **Parent Account**, Employees,
  Ownership, Industry, Account Type, Account Number, Account Site, Phone, Fax, Email, Rating,
  SIC Code, Annual Revenue, full **Billing Address** and **Shipping Address** blocks,
  Description.

**Creation & import.** Manual, Quick Create, Clone, import, API — and, most importantly,
**automatically as a by-product of lead conversion** whenever the lead's Company field is
populated.

**Validation behaviour.** Unique-field duplicate check (typically Account Name / Website /
Phone). `Parent Account` supports a company hierarchy, and Zoho propagates ownership changes
down it: "When the ownership of the parent record is changed the ownership of the associated
first-level and second-level child record will also change."

**What happens after creation.** The account becomes a hub with related lists: Contacts,
Deals, Quotes, Sales Orders, Invoices, Cases, Open/Closed Activities, Notes, Attachments,
Products.

**Who consumes account data.** Contacts (Account Name), Deals (**mandatory** Account Name),
Quotes / Sales Orders / Invoices (**mandatory** Account Name, plus the Billing and Shipping
address blocks are copied into every document), Cases. This is the clearest
*enter-once-use-everywhere* node in the entire schema: an address typed on the Account
surfaces on every quote, order and invoice for the rest of the relationship.

---

### Contacts

**What it is.** A person you have a real relationship with, normally attached to an Account.

**Why it exists.** Deals are agreed with people, not companies. Contacts hold the
communication channel (email/phone), the role, and the reporting structure inside the
customer's organisation.

**Fields.**
- *Required:* Last Name only. Note that **Account Name is *not* mandatory** — Zoho permits
  orphan contacts, e.g. for B2C.
- *Optional (standard):* Contact Owner, Salutation, First Name, Account Name, Vendor Name,
  Lead Source, Title, Department, Date of Birth, **Reporting To**, Email Opt Out, Skype ID,
  Phone, Mobile, Home Phone, Other Phone, Fax, Email, Secondary Email, Assistant, Asst Phone,
  Mailing Address block, Other Address block, Description.

**Creation & import.** Manual / Quick Create / Clone / import / Web-to-Contact / API /
**lead conversion** (which always creates a contact).

**Validation behaviour.** Email is the standard unique field. Duplicate alert on manual
create; Skip-or-Overwrite choice on import.

**What happens after creation.** The contact becomes the target of activities and emails, is
attached to Deals (Contact Name plus **Contact Role**), receives campaign membership, and can
be the reporting-to parent of other contacts.

**Who consumes contact data.** Deals (Contact Name), Quotes/Sales Orders/Invoices (Contact
Name), Cases (Related To), Campaigns (members), Activities, Notes.

---

### Deals (Opportunities / "Potentials")

**What it is.** A specific, quantified revenue opportunity with a company: an amount, an
expected close date, and a position in a sales-stage pipeline.

**Why it exists.** It is the **unit of forecasting**. Pipeline reporting, quota attainment,
win-rate analysis and revenue forecasting all derive from Deal records. Accounts tell you who
your customers are; Deals tell you what the business is worth and when.

**Fields.**
- *Required:* Deal Name, **Account Name**, Closing Date, Stage. Via the API, creating a deal
  during lead conversion additionally requires **Pipeline**.
- *Optional (standard):* Deal Owner, Type, Lead Source, Campaign Source, Contact Name, Amount,
  Next Step, Probability, **Expected Revenue**, Description.

**Auto-derived fields — the key pattern.** `Probability` is driven by `Stage` (a
stage-to-probability mapping), and `Expected Revenue` = Amount × Probability. This is Zoho's
canonical "enter once, derive the rest" mechanism: the rep picks a stage, and the forecast
number computes itself.

**Creation & import.** Manual / Quick Create / Clone / import / API / **lead conversion**
(optional "Create a new Deal for this Account/Contact" checkbox) / from an Account's or
Contact's related list.

**Validation behaviour.** Stage must come from the configured pipeline; Closing Date is
required so that every deal lands in a forecast period; Account Name must resolve to an
existing Account.

**What happens after creation.** The deal moves through stages (Kanban), accumulates
activities, produces Quotes → Sales Orders → Invoices, and feeds Forecasts and Dashboards.
Zoho layers **Blueprint** on top of Deals to enforce stage-transition process (Phase 2).

**Who consumes deal data.** Quotes / Sales Orders / Invoices (Deal/Potential Name), Cases
(Potential Name), Forecasts, Campaigns (ROI attribution via Campaign Source),
Reports/Dashboards.

---

## 1.3 Activity Management cluster

Zoho splits activities into **three separate modules** — Tasks, Calls, Meetings — rather than
one polymorphic "activity" table. They share a pattern: each links to a person (**Contact
Name**, or a lead) *and* to a business object (**Related To** — Account, Deal, Case, etc.),
and each appears on the parent record's **Open Activities** / **Closed Activities** related
lists.

### Tasks

**What it is.** A unit of work to be done by a specific date, with no fixed time slot.

**Why it exists.** Follow-up discipline. Anything that must not be forgotten becomes a task.

- *Required:* Subject.
- *Optional:* Task Owner, Due Date, Contacts/Leads, Accounts, Status, Priority, Send
  Notification Email, Remind At, Recurring Activity, Description.

**Behaviour.** A task is closed **only** when Status = Completed — it never auto-closes. Tasks
are deliberately **not shown on the CRM calendar**, because "they can be completed any time
within a specified interval; they are not scheduled for a specific time." Tasks support
recurrence and reminders.

**Consumed by.** Open/Closed Activities related lists on Leads, Contacts, Accounts, Deals and
Cases; activity reports (overdue tracking, time-to-close).

### Calls

**What it is.** A logged phone interaction, inbound or outbound — and also a *scheduled* call.

**Why it exists.** Calls are the highest-volume sales touch; logging them creates the
interaction history and the activity metrics that sales management runs on.

- *Required:* Subject, **Call Type** (inbound/outbound), Call Start Time, Call Duration.
- *Optional:* Call Purpose, Call From/To, Related To, Call Details, Description, Call Result.

**Behaviour.** Calls appear on the CRM calendar. `Call Result` records the outcome, which is
what makes call logs analysable rather than merely archival.

### Meetings (Events)

**What it is.** A scheduled interaction at a place and time, with invitees.

**Why it exists.** Calendar coordination, plus the meeting history on the customer record.

- *Required:* Subject, Start Date Time, End Date Time.
- *Optional:* Meeting Owner, Venue, Contacts/Leads, Accounts, Send Notification Email,
  Remind At, Recurring Activity, Description.

**Behaviour — an important asymmetry.** Meetings **auto-close**: "Meetings are considered to
be completed when the specified end time of the meeting passes, so they are automatically
marked as closed." Tasks require an explicit status change; meetings close on the clock. This
is a deliberate distinction between *intent-based* and *time-based* activities.

### Notes

**What it is.** Free-text commentary attached to a record. In Zoho, Notes are effectively a
**universal related list** rather than a first-class standalone module with its own
mandatory-field specification.

**Why it exists.** To capture context that does not fit a structured field — timestamped and
attributed — without inventing a custom field for every eventuality.

**Behaviour.** Notes attach to Leads, Contacts, Accounts, Deals, Cases and inventory records.
During lead conversion, notes are **automatically moved to the Deal** (if one is created) and
**copied to the Account and Contact**. Deleting a parent record deletes its notes: "When you
delete a record, all the associated child records including the notes and open/close
activities will also be deleted."

---

## 1.4 Inventory / Order Management cluster

### Products

**What it is.** A sellable (or purchasable) item or service in the catalogue.

**Why it exists.** So that what you sell is defined once, centrally, and every quote, order
and invoice references it instead of re-typing a description and a price.

- *Required:* Product Name.
- *Optional:* Product Owner, Product Code, Product Active, Vendor Name, Product Category,
  Sales Start/End Date, Support Start/Expiry Date, Commission Rate, Manufacturer,
  **Unit Price**, Taxable, Usage Unit, Handler, Description, and the stock block:
  **Qty Ordered, Qty in Stock, Reorder Level, Qty in Demand**.

**Consumed by.** Quotes, Sales Orders, Invoices, Purchase Orders (line items); Price Books;
Cases (Product Name); Deals (via product line items); Vendors.

**Not confirmed:** the exact mechanics by which Sales Orders and Purchase Orders mutate
`Qty in Stock` / `Qty Ordered` / `Qty in Demand` are not stated in the inventory overview
article. Treat Zoho's stock behaviour as unverified rather than assuming it.

### Price Books

**What it is.** A named set of list prices for products — customer-tier or volume-based
pricing.

**Why it exists.** Different customers pay different prices for the same product. Without a
price book, that variation lives in reps' heads and in inconsistent manual overrides.

- *Required:* Price Book Name.
- *Optional:* Owner, Active, **Pricing Model**, Description, and pricing detail rows
  (From Range, To Range, Discount) — i.e. volume tiers.

**A limitation worth noting.** Price Books link to **Products, not to Accounts/Contacts**. A
price book is selected on the *document* (quote/order/invoice), not automatically inferred
from the customer. This is a genuine gap in Zoho's "enter once" story, and a candidate for
deliberate S3K divergence.

### Quotes

**What it is.** A formal priced proposal — "legally binding agreements between a customer and
vendor to deliver the customer requested products in a specified time-frame at a predefined
price," valid until an expiry date.

**Why it exists.** It converts a deal's verbal number into a document that can be sent, signed
and audited, and it is the anchor for everything downstream.

- *Required:* Subject, Account Name, Product Name, Quantity, List Price (Unit Price is
  displayed from the product).
- *Optional:* Quote Owner, Potential (Deal) Name, **Quote Stage**, Valid Till, Contact Name,
  Carrier, Shipping, Inventory Manager, Billing Address block, Shipping Address block,
  Quantity in Stock, Total, Tax/Adjustments, Terms & Conditions, Description.

**Creation.** Manual, or **directly from the Deal or the Account page** — which is the whole
point: the account, contact, addresses and deal linkage come across without retyping.

**What happens after creation.** The quote is rendered through a customisable **Inventory
Template**, emailed/PDF'd/e-signed, then **converted with one click into a Sales Order or an
Invoice**. Zoho hides the Convert button once a quote has already been converted, keeping the
document chain single-path.

**Consumed by.** Sales Orders, Invoices, Deals (related list), reports.

### Sales Orders

**What it is.** A confirmed order — the customer has accepted the quote and issued a purchase
order.

**Why it exists.** It marks the commitment boundary between "proposal" and "obligation to
deliver", and carries fulfilment data (due date, carrier, status, pending quantity) that a
quote does not.

- *Required:* Subject, Account Name, Product Name, Quantity, List Price.
- *Optional:* SO Number, Potential Name, Customer No, **Purchase Order**, **Quote Name**,
  Contact Name, Due Date, Carrier, Pending, Status, Sales Commission, Excise Duty,
  Assigned To, both address blocks, Tax, Adjustments, Terms & Conditions, Description.

**Consumed by.** Invoices (Sales Order lookup), Purchase Orders, fulfilment reporting.

### Invoices

**What it is.** The bill issued to the customer.

**Why it exists.** Revenue recognition, collections, and closing the loop between sales
activity and money actually received.

- *Required:* Subject, Account Name, Product Name, Quantity, List Price, **Assigned To** —
  the only sell-side document that mandates an assignee, because someone must own collection.
- *Optional:* Invoice Number, **Sales Order**, Purchase Order, Customer No, Invoice Date,
  Due Date, Sales Commission, Excise Duty, Contact Name, Status, both address blocks, Total,
  Terms & Conditions, Description.

**Creation.** Manual, or converted from a Quote **or** a Sales Order.

### Purchase Orders (adjacent — the reverse flow)

Buys *from* a Vendor rather than selling to an Account. Required: Subject, **Vendor Name**,
Product Name, Quantity, List Price, Assigned To. Structurally identical to a Sales Order with
the counterparty swapped — which is exactly why Zoho can share one document engine across all
four inventory documents.

### Vendors

**What it is.** A supplier or partner organisation.

**Why it exists.** Products are sourced from someone; purchase orders are issued to someone.
Vendors are the Accounts-equivalent for the buy side.

- *Required:* Vendor Name.
- *Optional:* Vendor Owner, Phone, Email, Website, GL Account, Category, Vendor Address block,
  Description.

**Consumed by.** Products (Vendor Name), Purchase Orders (mandatory Vendor Name), Contacts
(Vendor Name field — a contact can belong to a vendor rather than an account).

---

## 1.5 Marketing & Support cluster

### Campaigns

**What it is.** A marketing initiative (trade show, webinar, email blast) with a budget, a date
range, and a set of members.

**Why it exists.** Attribution. Campaigns answer "which marketing spend produced which
pipeline", by linking spend → leads/contacts → deals.

- *Required:* Campaign Name.
- *Optional:* Campaign Owner, Type, Status, Start Date, End Date, **Expected Revenue**,
  **Actual Cost**, **Budgeted Cost**, Expected Response, Num Sent, Description.

**Campaign membership — the important structure.** Leads and Contacts are associated to a
campaign, and each association carries a **Campaign Member Status** ("Invited", "Sent",
"Received", "Attended", "Not Attended", …). The status lives on the *relationship*, not on the
lead or on the campaign — a genuine join entity with its own attributes. Members are added
from the campaign's related list, from the lead/contact record, or by import.

**Consumed by.** Leads and Contacts (Campaign related list), Deals (`Campaign Source` field —
this is what closes the ROI loop: budgeted cost vs. actual won revenue), reports.

### Cases (Tickets)

**What it is.** A post-sale support ticket capturing a customer issue, feedback or feature
request.

**Why it exists.** Sales and support share the same customer. Keeping cases in the CRM means
the account owner can see that a customer has five open complaints before trying to upsell
them. Zoho states the goal explicitly: integrating sales and post-sales support in a single
system enables faster resolution and "more cross-selling and up-selling opportunities in
future."

- *Required:* Subject (255 chars), Status, **Case Origin** (Email / Phone / Website).
- *Optional:* Case Number, Case Owner, Priority, Product Name, Reported By, Related To, Type,
  Email, Account Name, Potential Name, Phone, Case Reason, Description (32,000), Internal
  Comments, Solution, Add Comment.

**Creation.** Manual, import, **Web-to-Case** forms, email (including an Outlook plug-in).

**What happens after creation.** Assignment via workflow/assignment rules → follow-up →
resolution → **the verified answer is promoted into the Solutions module** for reuse.
**Case Escalation Rules** raise unresolved cases up a hierarchy on a time basis.

**Consumed by.** Accounts, Contacts, Deals and Products (all four link to Cases); Solutions;
support SLA reporting.

### Solutions

Knowledge-base articles. Required: Solution Title, Question, Answer. Fed by resolved Cases and
consumed by agents answering new Cases. In effect: "make each problem cost you only once."

---

## 1.6 Users, Roles, Profiles & Teams

Zoho separates *who you are in the hierarchy* from *what you are allowed to do* — two
orthogonal axes. This is the part most homegrown CRMs get wrong, by collapsing both into a
single `role` enum.

| Concept | Answers | Behaviour |
|---|---|---|
| **User** | Identity | Owns records; the default owner is the record's creator |
| **Role** | *Where in the org chart* | Hierarchical. A user can see the data of users **below** them. Peers at the same role **cannot** see each other's data by default ("the VP Engineering cannot access the VP Marketing data") |
| **Profile** | *What operations are permitted* | A permission set — import data, customise modules, add users, convert leads, mass delete, etc. Non-hierarchical |
| **Group** | *Ad-hoc team* | A cross-hierarchy collection of users, for sharing and assignment |
| **Territory** | *Market segmentation* | An alternative record-access axis based on criteria (region, industry, size) |
| **Data Sharing Rules** | *Exceptions* | Default access is **private** (owner + manager). Sharing rules selectively widen access by role, role-and-subordinates, or group |

**Key defaults worth adopting.**
- Record access is **private by default** and widened deliberately — not open by default and
  restricted later.
- Ownership defaults to the creator, but is a first-class mutable field on every module
  (`Lead Owner`, `Account Owner`, `Deal Owner`, …) and drives both visibility and
  notification.
- **Mass Transfer** exists as a first-class operation, including reassignment of *associated
  open activities* — because people leave and territories get rebalanced.
- Deleting or deactivating a user forces an ownership transfer, with no retention option.

**Permission-gated operations.** Convert Leads, Import, Mass Transfer, Mass Delete and Module
Customisation are all separate profile permissions; buttons are hidden or disabled rather than
failing on click.

---

## 1.7 Cross-cutting record operations

These apply to essentially every module and are as much a part of "what Zoho is" as the
schema:

| Operation | Behaviour |
|---|---|
| **Quick Create** | Inline mini-form asking only mandatory fields, usable from a related list, so creating a child record never navigates you away from the parent |
| **Clone** | Duplicate an existing record and edit — the fastest path for near-identical records |
| **Inline edit** | Edit a field from the detail or list view without entering edit mode |
| **Mass Update** | Update a field across many records by criteria. Multi-selects support Overwrite vs. **Append**. Cannot mass-update Text Area or Lookup fields |
| **Mass Transfer** | Reassign owner in bulk, optionally including associated open activities |
| **Mass Delete** | Criteria-based bulk delete; lands in the Recycle Bin |
| **Merge** | *Find and Merge* (criteria across up to six fields) and *De-duplicate* (auto-search on one of four fields per module) |
| **Recycle Bin** | Deleted records recoverable for **60 days** |
| **Cascade delete** | Deleting a parent deletes its notes and open/closed activities |
| **Selection limit** | Manual selection capped at 500 records; "select all records in this view" bypasses it |
| **Last Activity Time** | System-maintained; updated by edits, activities, emails, notes and ownership changes — but **not** by mass operations (except Mass Delete) or related-list edits |
| **Print / Templates** | Email Templates, Mail Merge Templates (Leads/Contacts/Accounts/Deals), Inventory Templates (Quote/SO/Invoice/PO) |

### Import workflow (all modules)

1. Upload CSV/XLSX. The file must be closed, and must not contain apostrophes.
2. **Apply Auto Mapping** matches file column headers to module fields; unmapped columns are
   fixed manually.
3. Choose the **matching field** for deduplication — the dropdown always offers the module
   **ID** first, then any fields configured as unique (e.g. Email for Leads/Contacts).
4. Choose the action: **Add only** / **Update only** / **Both** ("update the current record if
   a duplicate is found, and add a new record if not found").
5. If Update or Both, choose **"Don't update empty values for existing records"** — this
   protects populated data from being blanked by a sparse import file.
6. With the email-duplication check on, choose **Skip** or **Overwrite**. Choosing Overwrite
   means the Lead/Contact **ID cannot be mapped**, and the Clone option is disabled.
7. Import runs; a result summary reports created / updated / skipped / errored rows.

---

## 1.8 What Phase 1 establishes for S3K

Carrying forward into Phase 2 (flow and automation) and Phase 5 (blueprint):

1. **Minimum mandatory fields, maximum optional fields.** Zoho's required set is 1–4 fields per
   module. Friction at creation is the enemy; data completeness is an automation problem, not
   a validation problem.
2. **Lead/Contact separation is about data hygiene, not vocabulary.** The value is the
   qualification gate that sits before records enter the permanent database.
3. **Account is the aggregation point and the address source of truth.** Billing and shipping
   addresses entered once on the Account flow into every commercial document forever. This is
   the strongest "enter once, use everywhere" pattern in the product.
4. **Deals encode derivation, not just storage.** Stage → Probability → Expected Revenue is a
   computed chain, not three fields a rep types.
5. **A uniform document shape is what enables one-click conversion.** Quote, Sales Order,
   Invoice and Purchase Order share a header + line-item structure; that is *why* conversion is
   a button rather than a re-entry form.
6. **Activities split three ways with different closure semantics.** Tasks close manually,
   meetings close on the clock, calls are logged after the fact with a result.
7. **Membership relationships carry their own attributes.** Campaign Member Status and Deal
   Contact Role live on the join, not on either endpoint.
8. **Two orthogonal permission axes.** Role = hierarchy and visibility; Profile = permitted
   operations. Private by default, widened explicitly.
9. **Every module ships with bulk operations.** Import with update-vs-create semantics, mass
   update, mass transfer, merge, recycle bin. These are not "nice to have later" — without them
   a CRM is unusable at real data volumes.

---

## Sources — Phase 1

- [Standard Modules & Fields — Zoho CRM](https://help.zoho.com/portal/en/kb/crm/customize-crm-account/customizing-fields/articles/standard-modules-fields)
- [Standard Fields in Leads](https://help.zoho.com/portal/en/kb/crm/sales-force-automation/leads/articles/standard-fields-leads)
- [Converting Leads](https://help.zoho.com/portal/en/kb/crm/sales-force-automation/leads/articles/convert-leads)
- [Convert Lead API — Zoho CRM API v8](https://www.zoho.com/crm/developer/docs/api/v8/convert-lead.html)
- [Sales Activities — An Overview](https://help.zoho.com/portal/en/kb/crm/sales-force-automation/activities/articles/activities)
- [FAQs on Activities (Calls, Meetings, Tasks)](https://help.zoho.com/portal/en/kb/crm/faqs/activity-management/articles/faqs-on-activities)
- [Checking Duplicate Records in Zoho CRM](https://help.zoho.com/portal/en/kb/crm/manage-crm-data/duplication-management/articles/check-duplicate-records)
- [Common Operations with Records](https://help.zoho.com/portal/en/kb/crm/manage-crm-data/record-management/articles/common-operations-with-records)
- [Inventory Management — Introduction](https://help.zoho.com/portal/en/kb/crm/manage-inventory/introduction/articles/inventory)
- [Working with Quotes](https://help.zoho.com/portal/en/kb/crm/manage-inventory/quotes/articles/quotes)
- [Working with Price Books](https://help.zoho.com/portal/en/kb/crm/manage-inventory/price-books/articles/price-books)
- [Working with Cases](https://help.zoho.com/portal/en/kb/crm/customer-support/articles/working-with-cases)
- [Customer Support Overview](https://help.zoho.com/portal/en/kb/crm/customer-support/articles/customer-support)
- [Working with Campaigns](https://help.zoho.com/portal/en/kb/crm/marketing-automation-tools/campaigns/articles/campaigns)
- [Managing Roles](https://help.zoho.com/portal/en/kb/crm/security-control/role-management/articles/role-management-introduction)
- [Setting up Data Sharing Rules](https://help.zoho.com/portal/en/kb/crm/security-control/manage-data-sharing/articles/data-sharing-rules)
- [Field Meta Data API — v8](https://www.zoho.com/crm/developer/docs/api/v8/field-meta.html)

---

# Phase 2 — Data flow, relationships, and automation

Phase 1 catalogued the modules. Phase 2 asks the two questions that actually determine how much
typing a user has to do: **where does data move between modules**, and **what moves it
automatically**.

## 2.1 The master data-flow map

```
                    ┌──────────────┐
                    │  CAMPAIGNS   │──── Campaign Source ────┐
                    └──────┬───────┘                         │
                           │ membership (+ Member Status)    │
                           ▼                                 │
   web form ──▶ ┌──────────────┐                             │
   import   ──▶ │    LEADS     │                             │
   API      ──▶ └──────┬───────┘                             │
                       │ CONVERT (irreversible)              │
          ┌────────────┼────────────┐                        │
          ▼            ▼            ▼                        │
   ┌───────────┐ ┌──────────┐ ┌──────────┐                   │
   │ ACCOUNTS  │◀│ CONTACTS │ │  DEALS   │◀──────────────────┘
   └─────┬─────┘ └────┬─────┘ └────┬─────┘
         │ Account    │ Contact    │ Deal / Potential
         │ Name +     │ Name       │ Name
         │ addresses  │            │
         └────────┬───┴────────────┘
                  ▼
          ┌───────────────┐   convert   ┌──────────────┐  convert  ┌──────────┐
          │    QUOTES     │────────────▶│ SALES ORDERS │──────────▶│ INVOICES │
          └───────┬───────┘             └──────┬───────┘           └──────────┘
                  │ line items                 │
                  ▼                            ▼
          ┌───────────────┐            ┌────────────────┐
          │   PRODUCTS    │◀───────────│ PURCHASE ORDER │───▶ VENDORS
          └───────┬───────┘            └────────────────┘
                  │ list price
                  ▼
          ┌───────────────┐
          │  PRICE BOOKS  │
          └───────────────┘

   ACTIVITIES (Tasks / Calls / Meetings / Notes) attach to
   Leads, Contacts, Accounts, Deals, Cases — via "Related To" + "Contact Name"

   CASES ──▶ SOLUTIONS      (Accounts / Contacts / Deals / Products all link to Cases)
```

Read the graph as three chains plus a mesh:

1. **The acquisition chain** — Campaign → Lead → (Account + Contact + Deal). One-way,
   irreversible, and the point at which unqualified data becomes qualified data.
2. **The commercial chain** — Deal → Quote → Sales Order → Invoice, with Products and Price
   Books feeding line items, and Vendors feeding the reverse (Purchase Order) flow. It is
   single-path: Zoho hides the Convert button once a document has been converted.
3. **The service chain** — Case → Solution, hanging off Account/Contact/Deal/Product.
4. **The activity mesh** — Tasks, Calls, Meetings and Notes attach to almost everything and
   belong to nothing.

---

## 2.2 Lead conversion — copied vs. linked vs. left behind

This is the highest-leverage data movement in any CRM, so it is worth spelling out exactly.

**Trigger.** A user with the *Convert Leads* profile permission clicks Convert on a lead.

**What gets created:**

| Record | Created when | Notes |
|---|---|---|
| **Contact** | Always | Never optional |
| **Account** | Only if the lead's **Company** field is populated | This is why Company is mandatory on Leads |
| **Deal** | Only if "Create a new Deal for this Account/Contact" is ticked | Requires Deal Name, Closing Date, Stage, Pipeline |

**Field mapping — COPIED (value duplicated into the new record):**

| Lead field | → Contact | → Account | → Deal |
|---|:--:|:--:|:--:|
| Salutation, First/Last Name | yes | | |
| Designation / Title | yes | | |
| Phone, Mobile, Fax, Email, Skype ID | yes | yes (Phone, Fax) | |
| Address block | yes (Mailing) | yes (Billing) | |
| Email Opt Out | yes | | |
| Company Name | | yes (Account Name) | |
| Industry, Annual Revenue, Website, No. of Employees | | yes | |
| Lead Source | | | yes |
| Rating | | | yes |
| Custom fields | configurable via **Lead Conversion Mapping** — type *and* length must match | | |

**LINKED (relationship created, not copied):** the new Contact links to the new Account; the
Deal links to both. Campaign memberships carry across as relationships.

**MOVED vs COPIED — a subtle and important distinction:**
- **Notes** are *moved* to the Deal when a deal is created, and *copied* to the Account and
  Contact.
- **Attachments** are *moved* to exactly one destination — the user picks Contact, Account or
  Deal at conversion time.
- **Tags** are *carried over* (opt-in; `carry_over_tags` in the API) to all three.

**LEFT BEHIND / LOST:**
- The Lead record itself becomes permanently converted — "A lead cannot be reverted once
  converted to contact or account."
- Custom mandatory fields on **non-Standard layouts are not processed** during conversion. This
  is a documented sharp edge: carefully configured required fields silently do not apply.
- Lead Status has no destination — the qualification history is not preserved as structured
  data on any of the three new records.

**Existing-record matching (dedup at conversion).** Before creating anything, Zoho searches for
matches in this priority order:

1. **Unique fields** (phone, website, SSN, …) — checked first, Contacts before Accounts
2. **System fields** — Email (against Contacts), Company name (against Accounts), Lead name
   (against Contacts)

If a match is found, the user chooses **"Add to existing"** or **"Create new."** Via the API you
can force the outcome by passing an explicit `Accounts` / `Contacts` record ID.

**Failure modes.** Conversion is refused for: already-converted leads; records locked by Zia
image validation or an in-flight merge; records awaiting workflow approval; and any duplicate
collision on a unique field.

**Ownership and notification.** New records inherit the Lead Owner by default; `assign_to`
overrides it. `notify_lead_owner` and `notify_new_entity_owner` control emails. A user with
read-only permission on a matched Account *can still convert*, but "the fields in the account or
contact records will not be updated" — a silent partial success.

---

## 2.3 Module dependency map

Which modules cannot function without which:

| Module | Hard dependency (mandatory FK) | Soft dependency (optional lookup) |
|---|---|---|
| Leads | — (standalone by design) | Campaigns |
| Accounts | — | Parent Account (self), Vendors |
| Contacts | — (Account is optional) | Accounts, Vendors, Reporting To (self), Campaigns |
| **Deals** | **Accounts** | Contacts, Campaigns, Leads (source) |
| Tasks / Calls / Meetings | — | Leads, Contacts, Accounts, Deals, Cases |
| Notes | parent record (polymorphic) | — |
| Products | — | Vendors |
| Price Books | — | Products |
| **Quotes** | **Accounts + Products** | Deals, Contacts, Price Books |
| **Sales Orders** | **Accounts + Products** | Quotes, Deals, Contacts |
| **Invoices** | **Accounts + Products + Assigned To** | Sales Orders, Quotes, Deals, Contacts |
| **Purchase Orders** | **Vendors + Products + Assigned To** | Contacts |
| Campaigns | — | Leads, Contacts |
| Cases | — | Accounts, Contacts, Deals, Products |
| Solutions | — | Products |

**The load-bearing node is Accounts.** Four modules cannot be created without one, and
everything commercial hangs off it. Deals, Quotes, Sales Orders and Invoices are all inert until
an Account exists — which is precisely why "Account first" is the natural creation order, and
why lead conversion auto-creates the Account rather than asking for it.

**The most surprising design choice:** Contacts do *not* require an Account. Zoho keeps the
person/company link optional so that B2C and pre-qualification cases work. That optionality is
what lets a Contact exist while an Account does not — but it also means the Deal-creation UX has
to handle "this contact has no company yet."

---

## 2.4 Copy vs. link vs. derive — the three mechanisms

Every piece of data that appears in more than one place got there by one of three mechanisms,
and choosing the wrong one is the root cause of most CRM data problems.

| Mechanism | Example in Zoho | Behaviour when the source changes | When to use |
|---|---|---|---|
| **LINK** (foreign key) | Deal → Account Name; Quote → Deal | Always current; single source of truth | Identity and relationships |
| **COPY** (snapshot) | Account billing address → Quote billing address; Product Unit Price → Quote List Price | Frozen at the moment of copy | Anything that must be legally or historically accurate at a point in time |
| **DERIVE** (computed) | Stage → Probability; Amount × Probability → Expected Revenue; line items → Total; rollup summary fields | Recomputed on read/write | Anything that is a pure function of other fields |

Zoho's choices here are deliberate and worth copying wholesale:

- **Addresses on documents are COPIED, not linked.** An invoice issued to an old address must
  keep showing the old address. Linking would rewrite history.
- **Prices on line items are COPIED.** A quote at last quarter's price must remain valid at last
  quarter's price even after the catalogue is repriced.
- **Relationship identity is LINKED.** Renaming an Account renames it everywhere.
- **Anything arithmetic is DERIVED.** Totals, probabilities, expected revenue, rollups.

The one place Zoho *fails* its own test: **Price Books attach to Products, not to Accounts.** A
customer's pricing tier is neither linked nor derived — it is re-selected by hand on every
document. That is a genuine "enter it again every time" hole, and a strong candidate for
deliberate S3K divergence.

---

## 2.5 Zoho's automation catalogue — Trigger → Condition → Action → Result

Zoho has roughly nine distinct automation mechanisms. Presented uniformly:

### 1. Workflow Rules — the general-purpose engine

| | |
|---|---|
| **Trigger** | Record Created / Created or Edited / Edited / Field Update / Deleted; also on a date field |
| **Condition** | Criteria filter: all records, records matching criteria, or records *not* matching. Multiple conditions combinable |
| **Action** | **Instant:** up to 5 email alerts, 5 tasks, 3 field updates, 1 custom function, 1 webhook. **Time-based:** the same action types, scheduled relative to Rule Trigger Date, Created Time, Modified Time, or any date/time field in the module |
| **Result** | Fields updated, tasks created, emails sent, external systems notified |

**Why it matters for S3K:** the instant/time-based split is the whole game. "Assign a follow-up
task now" and "if still untouched in 3 days, email the manager" are the same rule.

### 2. Assignment Rules — automatic ownership

| | |
|---|---|
| **Trigger** | A record enters CRM via **import, web form, or API** |
| **Condition** | Ordered rule entries, each with up to 25 criteria; field-to-value or field-to-field comparison |
| **Action** | Assign to a user, role, or group. Multiple targets means **round-robin** distribution |
| **Result** | Record Owner set. A default user catches records when the target is unavailable, deactivated or deleted, so nothing is ever left unassigned |

**Critical limitation, and a design lesson:** "You cannot use Assignment Rules if you are
creating the Records manually." Manual creation bypasses assignment entirely — the owner is just
whoever typed it. Modules covered: Leads, Contacts, Accounts, Deals, Tasks, Cases, custom and
team modules.

### 3. Scoring Rules — automatic prioritisation

| | |
|---|---|
| **Trigger** | Field values changing, or activity/engagement signals accumulating |
| **Condition** | Per-rule criteria including time-windowed operators ("attended calls in the last 20 days") |
| **Action** | Add or subtract points |
| **Result** | A score field on the record: *Conversion score* (from related-module data), *Engagement score* (Calls, Emails, Meetings plus incoming signals), *Health score* (products purchased, deals, communications, tickets, campaigns) |

Limits: 5 scoring rules per account (Enterprise), 10 (Ultimate).

### 4. Blueprint — process enforcement on the record itself

| | |
|---|---|
| **Trigger** | A record enters a defined **State** (e.g. a deal stage) |
| **Condition** | Only the configured **Transitions** out of that state are offered, and only to the designated transition owner |
| **Action** | *Before* — who may perform it. *During* — mandatory fields, notes, checklists and widgets the user must complete. *After* — field updates, alerts, tasks, webhooks, functions |
| **Result** | The record moves to the next state having satisfied the requirements. Illegal transitions are simply not available in the UI |

Zoho's framing: a Blueprint is "an online replica of a business process." The problem it solves
is stated plainly — "When the process you follow offline is not captured in the software
accurately, there is no assurance that it is followed in the right manner."

**Workflow vs. Blueprint — the distinction that matters:** a workflow rule *reacts* to a change
that already happened; a Blueprint *gates* the change before it happens. Workflow is
after-the-fact automation; Blueprint is before-the-fact process control. Requires the *Manage
Automation* profile permission.

### 5. Validation Rules — data quality at the gate

| | |
|---|---|
| **Trigger** | Attempting to save a record |
| **Condition** | Acceptable values defined per field |
| **Action** | Allow the save, or reject it with a customisable error message |
| **Result** | Bad data never reaches the database |

Two documented limitations that matter: validation rules **do not execute for fields that are
read-only for any profile**, and (per Zoho's FAQ) "custom-created fields cannot be validated
through validation rules" — only system-defined fields. Requires the *Module Customization*
permission.

### 6. Approval Processes — human gates

| | |
|---|---|
| **Trigger** | Record submitted for approval (manually, or automatically by criteria — e.g. a duplicate arriving via web form is auto-submitted even when lead approval is off) |
| **Condition** | Criteria determine which records need approval, and who approves |
| **Action** | Approver approves or rejects; per stage you can attach one email alert, one webhook, one custom function, plus a task and a field update |
| **Result** | Record released into normal circulation or held. Approval History is retained under My Jobs → Approval Process |

### 7. Case Escalation Rules — time-based SLA enforcement

| | |
|---|---|
| **Trigger** | A case is not attended to by its assignee within a threshold |
| **Condition** | Ordered rule entries with criteria and escalation intervals, evaluated against the organisation's configured **Business Hours** |
| **Action** | Reassign up the hierarchy and/or notify via an email template, with additional recipients |
| **Result** | Nothing rots silently in a queue |

Notable constraint: **only one escalation rule can be active at a time**, unlike workflow
time-based actions which run concurrently. Requires the Escalation Scheduler to be enabled.

### 8. Rollup Summary Fields — aggregation without code

| | |
|---|---|
| **Trigger** | A child record in a related list is created, updated or deleted |
| **Condition** | Choice of related list and aggregate property (count, sum, min, max, avg) |
| **Action** | Recompute the parent's rollup field |
| **Result** | e.g. total open deal value on an Account; number of cases on a Contact |

Limits: Enterprise 10 per module, Ultimate 15. **Rollup fields cannot be used directly inside
formula expressions** — the documented workaround is a shadow field updated by a workflow that
fires on Rollup Update, which is exactly the kind of ceremony a purpose-built system should not
inherit.

### 9. Macros — one-click batches of manual actions

A saved bundle of actions (send an email, create a task, update fields) applied to selected
records on demand. Not event-driven — it is a shortcut for the repetitive manual sequence a rep
performs dozens of times a day.

---

## 2.6 The automation execution order

Zoho publishes the sequence in which these engines fire when a record enters the system. This is
the single most reusable engineering detail in Phase 2, because getting the order wrong produces
bugs that are nearly impossible to diagnose:

```
1. Assignment Rules      → record gets an owner
2. Review Process        → optional data-quality gate
3. Scoring Rules         → record gets a score
4. Workflow Rules        → reactive automation fires
5. Approval Process      → human gate, if criteria met
6. Blueprint             → process state machine engages
7. Scoring Rules (again) → rescored after all the above
8. CommandCenter         → cross-module journey orchestration
```

Three things to take from this:

- **Ownership is assigned first**, before anything else — because almost every subsequent rule
  and notification needs to know who the owner is.
- **Scoring runs twice**, before and after workflows, so that scores reflect fields that
  workflow rules themselves populated.
- **Validation rules are not in the list.** They operate outside this pipeline, at save time —
  they are a precondition, not a stage.

---

## 2.7 Where Zoho's automation still leaves manual work

Honest assessment of the reference implementation, so that S3K does not inherit its gaps:

| Gap | Consequence | Opportunity for S3K |
|---|---|---|
| **Assignment rules skip manual creation** | The most common creation path is the one with no automatic ownership routing | Run assignment on *every* creation path, not just import/API |
| **Price Books do not attach to customers** | Rep re-picks the pricing tier on every quote, order and invoice | Attach a default price book / discount tier to the Account and inherit it |
| **Rollups cannot feed formulas** | Requires shadow fields plus a workflow to do arithmetic on an aggregate | Compute derived values in the query/service layer where composition is free |
| **Custom mandatory fields ignored on lead conversion (non-standard layouts)** | Silent data loss at the single most important transition | Validate the conversion target's full required set before committing |
| **Lead Status is discarded on conversion** | Qualification history is lost | Persist the pre-conversion state on the resulting records |
| **Hard limits everywhere** (5 alerts, 3 field updates, 2 unique fields, 5–10 scoring rules, 1 escalation rule) | Complex processes get split across multiple rules that are hard to reason about | Limits are a SaaS-tenancy artefact; a single-purpose product need not adopt them |
| **Read-only permission still permits conversion** | Silent partial success — record converted, fields not updated | Fail loudly, or elevate deliberately |

---

## 2.8 What Phase 2 establishes for S3K

1. **Conversion is the product's most important transaction.** It is multi-record, partially
   irreversible, dedup-sensitive and permission-gated. It deserves to be a single atomic service
   operation with explicit mapping configuration — not three sequential API calls from the UI.
2. **Accounts is the load-bearing node.** Creation order follows dependency order.
3. **Copy / link / derive is a per-field decision** with legal and historical consequences.
   Addresses and prices on documents must be snapshots; identity must be linked; arithmetic must
   be computed.
4. **Ownership assignment must be the first automation to run**, on every entry path.
5. **Reactive automation (workflow) and preventive process control (blueprint) are different
   tools.** Most homegrown CRMs build only the first and then wonder why the process is not
   followed.
6. **Time-based actions are as important as instant ones.** Follow-up, escalation and decay all
   depend on "if nothing happens by X, do Y" — which requires a scheduler, not just event hooks.
7. **A documented execution order is a requirement, not a nicety.** Assignment → scoring →
   workflow → approval → blueprint → re-score.

---

# Phase 3 — Creation forms, imports, and UX patterns

Phases 1 and 2 covered *what* the data is and *how it moves*. Phase 3 covers the part users
actually touch: the form, the importer, and the screens where work happens. The lens is
**workflow efficiency — keystrokes and navigations eliminated** — not visual design.

## 3.1 Form structure: the Page Layout system

Zoho does not have "a create form per module." It has a **layout system**, and the create form
is a rendering of a layout.

| Concept | What it is | Why it exists |
|---|---|---|
| **Page Layout** | A named arrangement of sections and fields for a module | One module, several business processes. Zoho's own example: a mobile retailer whose Cases module serves both *sales* and *service* — "The assessment of requirements for sales is different from that of mobile service." |
| **Section** | A titled group of fields within a layout | Chunking; a 40-field form is unusable as one list |
| **Layout Rules** (Conditional Layouts) | Show/hide fields and sections, and **make fields mandatory**, based on a trigger field's value | Progressive disclosure — the form only asks what is relevant to the path the user has chosen |
| **Quick Create form** | A cut-down, layout-specific form | Create a child record without leaving the parent |
| **Business Card view** | Up to **5 fields** pinned at the top of the detail page | The "who am I looking at" summary |
| **Subform** | A repeating child table inside a record (e.g. line items) | One-to-many data that belongs to the record, not a separate module |

**Layout-specific everything.** A layout controls not just which fields appear but also which
**picklist values** are available, which **related lists** show, and what the detail view looks
like — "the detail view … is layout specific so you can create different detail view for each
layout." The mobile-retail example has sales-specific stages in one layout and service-specific
stages in the other, in the same module.

**Layouts are assigned to profiles**, with a default layout per profile. So a support agent and
a salesperson open the same module and get different forms.

**Records can be moved between layouts by automation.** Zoho's documented pattern: a workflow
field-update rule that switches the layout when a field changes — "If this field is updated to
'Faulty device', the layout should be updated to Mobile Service." The record keeps its data and
adopts the new layout's fields, picklist values and rules. This is a genuinely powerful idea:
*the form follows the record's state, automatically.*

**Layout Rules in practice.** "Fields can be made mandatory or shown based on the value entered
by the user." Zoho's example: selecting "repair" reveals *Model Number* and makes *Warranty
Period* mandatory. Note the scope limit — on **Quick Create forms only "show fields" and "set
mandatory fields" actions apply**; the full rule set works only on the main layout.

**Why this matters for S3K.** The alternative to a layout system is a hard-coded form per
module, which forces either a bloated form that asks everyone everything, or a code change every
time the process changes. Layout rules are how Zoho keeps mandatory-field counts low (Phase 1's
finding) while still collecting rich data: *ask nothing up front, then ask precisely what the
chosen path requires.*

---

## 3.2 Field behaviour at creation time

How a field gets a value without the user typing it — the mechanisms, ranked by how much work
they save:

| Mechanism | Behaviour | Zoho example |
|---|---|---|
| **System default** | Value set by the system on insert | Record Owner = creator; Created By / Modified By; Created Time |
| **Static default value** | Configured constant | Lead Status = "Not Contacted"; Currency |
| **Context inheritance** | Value taken from the parent when created from a related list | Creating a Contact from an Account pre-fills Account Name; creating a Quote from a Deal pre-fills Account, Contact, Deal and both address blocks |
| **Lookup** | A typeahead reference to another record; stores an ID, displays a name | Deal → Account Name; Quote → Product Name |
| **Lookup-driven copy** | Selecting a lookup pulls other fields across | Selecting a Product on a quote line pulls Unit Price → List Price |
| **Picklist dependency** | The options in field B are filtered by the value of field A | Country → State |
| **Layout rule** | Field appears / becomes mandatory based on another field | "repair" reveals Model Number |
| **Formula field** | Read-only, computed from other fields on the record | Expected Revenue = Amount × Probability |
| **Rollup summary** | Read-only, aggregated from a related list | Total open deal value on an Account |
| **Auto Number** | System-generated sequence | Case Number, Invoice Number, SO Number |
| **Hidden field with default** | Populated invisibly at capture time | Web form sets Lead Source = "Website" or "blog" per site |
| **Assignment rule** | Owner set by routing logic | Round-robin across a team (import/webform/API only) |
| **Scoring rule** | Priority computed from criteria and engagement | Lead Score |

Two important constraints Zoho documents:

- **Web forms cannot use Lookup, Auto Number or Formula fields.** Supported types are Text,
  Integer, Percentage, Decimal, Currency, Date, Date/Time, Email, Phone, Picklist, URL,
  Text Area, Checkbox and Multi-select Picklist. This is why web-captured records land in
  *Leads* (flat, no required relationships) rather than directly in Contacts + Accounts + Deals.
- **Validation rules do not run on fields that are read-only for any profile** — a real trap
  where a "safe" read-only setting silently disables the guard.

**Duplicate detection at the moment of creation** (from Phase 1, restated as UX): manual create
raises a *duplication alert* — one match offers to open the matching record, several matches
suggest a merge. Web form duplicates are pushed into an **approval queue** rather than rejected.
API creates are hard-rejected. Three different behaviours for three different contexts, and all
three are defensible: a human can adjudicate, a website visitor cannot be shown an error about
your database, and an integration should fail loudly.

---

## 3.3 The import workflow, in full

Import is where a CRM either earns or loses a customer's trust, because it is the first thing
they do and it operates on data they cannot afford to lose.

### Limits and formats

| | |
|---|---|
| **Formats** | CSV, XLS, XLSX, VCF. Migration also accepts ZIP (up to 10 GB or 200 CSVs) |
| **Batch size** | Free 1,000 · Standard 5,000 (unlimited via CSV) · Professional 20,000 · Enterprise 30,000 |
| **Rule** | "If you want to import more than 5000 records, the file should be in CSV format" |

### The steps

1. **Upload.** File must be closed; no apostrophes; header row required in row 1.
2. **Map fields.** *Apply Auto Mapping* matches headers to fields; the rest is manual. Users can
   **create new CRM fields during the import**, and **map multiple CRM fields to one import
   column**.
3. **Choose the matching field** for deduplication. The dropdown offers the record **ID** first,
   then the module's unique fields. Zoho's documented per-module defaults:

   | Module | Default duplicate-check field |
   |---|---|
   | Leads / Contacts | Email |
   | Accounts | Account Name |
   | Deals | Deal Name |
   | Cases | Subject |
   | Products | Product Name |

   Record IDs (obtained by exporting first) are the reliable option for a round-trip edit.
4. **Choose the action:** *Add as new* (skipping duplicates) · *Update existing only* ·
   **Both** — "update the current record if a duplicate is found, and add a new record if not."
5. **Protect existing data:** tick **"Don't update empty values for existing records."** Without
   this, a sparse spreadsheet blanks populated fields. This single checkbox prevents the most
   common catastrophic import.
6. **Assign owners.** Three mechanisms: assign everything to one user; run **Lead Assignment
   Rules** with criteria; or map the owner from a column in the file.
7. **Run**, then review the result summary: created / updated / skipped / failed.

### Error handling

Zoho enumerates the common failure causes — missing header row, empty mandatory fields, wrong
character encoding, date/time format mismatch, empty rows, and **picklist values that do not
already exist in CRM**. That last one is a real design decision: the importer will not silently
invent new picklist options.

Overwrite semantics are narrow and safe: **"only the mapped fields will be overwritten."**

### Undo — the feature most homegrown CRMs skip

- **Import History** under Setup → Data Administration → Import shows every import and whether
  it succeeded.
- **"Undo This Import"** permanently deletes the records that import created.
- **It is not reversible**, and after **30 days** the import auto-confirms and can no longer be
  undone.
- **Undo cascades**: undoing imported Contacts also removes the Accounts they created, and
  vice versa.

That is the correct model — a bounded regret window on a bulk operation, with explicit cascade
semantics — and it is worth adopting wholesale.

**Notes are a special case:** they must attach to existing records, so a notes import requires
either the parent's email address or its Record ID.

---

## 3.4 Web forms as a creation path

Web-to-Lead / Web-to-Contact / Web-to-Case turn a public page into a record-creation endpoint.
The parts that matter as design patterns:

- **Hidden fields with default values.** Invisible to the visitor, submitted with the payload.
  Zoho's documented use: deploy the same form on several sites with `Lead Source` defaulted to
  "Website" on one and "blog" on another. Attribution is captured with zero user effort — a
  clean example of *enter once (at configuration time), use forever*.
- **Auto-response rules** send a templated acknowledgement to the submitter automatically.
- **Duplicates route to approval**, not to an error page.
- **Assignment rules fire** (web forms being one of the three qualifying entry paths).
- **CAPTCHA** is available; Zoho's own community threads acknowledge its spam resistance is
  contested — worth noting rather than assuming the reference implementation is adequate here.

---

## 3.5 Working-surface UX patterns

The patterns below are the ones that change how much work a user does. Visual styling is
excluded deliberately.

### Module views

| View | What it is | Efficiency it buys |
|---|---|---|
| **List view** | Filterable, sortable table | Scan, filter, sort, prioritise, and act in bulk |
| **Kanban view** | Cards in columns, grouped by a "Categorize by" field | See process position at a glance; **drag a card to change the record's stage** |
| **Canvas views** (custom list / tile / table) | Designer-built record templates | Density and information hierarchy tuned per team |

**Kanban specifics worth copying:**
- Columns come from any picklist ("Categorize by") — so one module supports several boards
  (Leads by Status, Deals by Stage).
- **"Aggregate by"** sums a numeric column per stage — integer, decimal, currency, formula or
  rollup — so the board shows pipeline value per stage, not just card counts. Dragging a card
  updates both the record and the column total.
- Cards show a configurable field set; columns collapse; cards can be dropped onto collapsed
  columns.
- Mass actions work from the board: bulk email, create task, change owner, update field.
- Supported on most modules — the documented exceptions are Socials, Visits, activities and
  finance modules.

### Record-level patterns

| Pattern | Behaviour | Manual work eliminated |
|---|---|---|
| **Related lists** | Child records (Contacts, Deals, Quotes, Activities, Notes, Attachments) rendered on the parent's detail page | No searching for children; no context switching |
| **Quick Create from a related list** | Mini-form asking only mandatory fields, with the parent link pre-filled | Removes a navigation round trip *and* the re-entry of the parent link |
| **Create-from-parent** | New Quote from a Deal inherits Account, Contact, Deal and both address blocks | The single biggest keystroke saving in the product |
| **Inline editing** | Edit a field from list or detail view without an edit mode | Removes the open → edit → save → close cycle for one-field changes |
| **Clone** | Duplicate and amend | Fastest path for near-identical records |
| **Open / Closed Activities** | Automatic split of the activity list by completion | "What is outstanding on this account" without a filter |
| **Macros** | A saved bundle of actions (email + task + field update) run on demand against selected records | Collapses a repeated multi-step manual sequence into one click |
| **Business card** | Up to 5 pinned key fields | Identification without scrolling |

### Bulk patterns (restated from Phase 1, as a UX requirement)

Mass Update (Overwrite vs. **Append** for multi-selects), Mass Transfer (optionally including
open activities), Mass Delete, Find-and-Merge / De-duplicate, and a **60-day Recycle Bin**.
Manual selection caps at 500 records; "select all in this view" bypasses it.

---

## 3.6 The efficiency principles behind the patterns

Stripping the specifics away, Zoho's UX obeys five rules that are worth stating as design
constraints for S3K:

1. **Never navigate away to create a child.** Quick Create from a related list, with the parent
   pre-linked. Every "go to the other module, create, come back, link" round trip is a bug.
2. **Creating from a parent inherits everything the parent knows.** Quote-from-Deal is the
   canonical case: account, contact, addresses and deal link all arrive free.
3. **The form asks only what this path needs.** Tiny mandatory sets plus layout rules that
   reveal and require fields conditionally.
4. **Direct manipulation beats form editing.** Drag a Kanban card to change stage; edit inline
   to change one field. Opening an edit form should be the exception.
5. **Every bulk action has an undo or a safety net.** Recycle Bin, Undo This Import, "don't
   update empty values," and duplicate alerts before rather than after the damage.

---

## 3.7 Where Zoho's UX still costs the user work

| Friction | Why it happens |
|---|---|
| Assignment rules do not run on manual creation | The most common creation path gets no routing |
| Price book re-selected on every document | Pricing tier is not held on the customer |
| Layout rules on Quick Create are limited to show/mandatory | The quick path cannot express the full form logic |
| Web forms cannot use lookup fields | Web-captured data must land in a flat module (Leads) and be reconciled later |
| Rollup fields unusable in formulas | Shadow field + workflow ceremony for basic arithmetic |
| Picklist values must pre-exist before import | Safe, but means an import can fail late on a data-dictionary issue |
| 500-record manual selection cap | Arbitrary; bulk work needs the "select all in view" escape hatch |

---

## 3.8 What Phase 3 establishes for S3K

1. **The create form should be data-driven, not hard-coded.** Sections + conditional rules are
   what let mandatory sets stay tiny while the data stays rich.
2. **Context inheritance is the highest-value single feature.** "New X from Y" must pre-fill
   everything Y knows. This is the direct answer to the enter-once question.
3. **Import needs matching-field selection, add/update/both semantics, "don't update empty
   values," an error report, and a bounded undo window.** Anything less is not an importer, it
   is a data-loss mechanism.
4. **Duplicate handling should differ by entry path** — alert a human, queue a web submission,
   reject an API call.
5. **Kanban with per-column aggregation is the sales-team working surface**, and drag-to-update
   is the cheapest possible way to advance a pipeline.
6. **Inline edit and quick create remove whole navigation cycles**, which is where the day
   actually goes.
7. **Hidden defaulted fields capture attribution for free** at configuration time.

---

# Phase 4 — S3K vs Zoho differentiation

Phases 1–3 described Zoho. Phase 4 describes **S3K as it actually is**, from the code, and
establishes what may and may not be ported. Nothing here is inferred from the architecture
documents alone; every claim names the file it came from.

## 4.0 Which tree is the product — a required preliminary

The repository has two materially different states, and analysing the wrong one would invalidate
everything downstream:

| Branch | Backend state |
|---|---|
| `claude/s3k-zoho-analysis-665674` (this worktree's checkout) | **Scaffold only.** One migration (`20260804_1400_0001_initial_schemas_and_extensions.py`) creating the `platform` and `crm` schemas, `pgcrypto`, `pg_trgm` and a throwaway `tenant_isolation_probe` table. Every CRM `models.py` is a docstring saying "Placeholder — no tables are defined yet." |
| **`feat/platform-phase1-crm-core`** | **The real product.** Nine migrations, including `platform_identity_rbac_and_crm_core`, `lead_conversion_product_interest`, `teams_departments_and_view_team`, `crm_search_vectors_and_indexes` and `product_entitlements`. Full models, services, repositories, routers and an integration test suite. |

**All Phase 4/5/6 analysis below is of `feat/platform-phase1-crm-core`.** The current checkout
also still carries the pre-platform prototype (`app/(crm)/`, `features/`) at the repository root,
alongside the newer `frontend/` — the tree contains two generations of the product at once.

Restating the stack correction from the header: **FastAPI + SQLAlchemy 2.0 async + Alembic on
PostgreSQL, with row-level security.** The `04-`/`05-` Prisma schema documents are a *logical*
model only; `00-EXECUTIVE-SUMMARY.md` says so explicitly — "implement as SQLAlchemy models per
foundation plan."

---

## 4.1 Who S3K CRM is actually for

Zoho CRM is a **general-purpose, infinitely configurable CRM sold to anyone**, from a two-person
consultancy to a multinational, across every industry, in editions from Free to Ultimate. Almost
every design decision in Phases 1–3 follows from that: page layouts per profile, custom modules,
conditional layouts, two-unique-fields-per-module limits, five-scoring-rules ceilings, an
inventory suite, a helpdesk, and a marketing suite — all in one product, all switchable.

S3K CRM is something else:

| Dimension | Zoho CRM | S3K CRM (from the code and `03-S3K-CRM-ARCHITECTURE.md`) |
|---|---|---|
| **Product shape** | A standalone CRM that tries to cover the whole business | **One product inside a multi-product platform.** `backend/app/products/crm/` sits beside `backend/app/platform/`; `platform/products/router.py` exposes `/entitlements` that gate access |
| **Scope boundary** | Sales + marketing + inventory + support + light finance | **Lead acquisition through opportunity closure, and nothing else.** The architecture doc explicitly excludes accounting/invoicing → S3K Books, contracts → S3K Contracts, support tickets → S3K Support, projects → S3K Projects, HR → S3K HR |
| **Configurability** | The customer builds their own CRM | **A fixed, opinionated model.** Modules are Python packages; statuses are native PostgreSQL enums; there is no custom-field or layout engine |
| **Tenancy** | Multi-tenant SaaS, isolation invisible to the customer | **Multi-tenant with isolation as a first-class product concern** — `organization_id` on every CRM table, PostgreSQL RLS, a schema audit that fails the build on an unclassified table |
| **Permission model** | Role hierarchy + Profile permission sets + territories + sharing rules | **Three system roles** (Admin / Manager / User) over a `module.ACTION` permission catalogue, plus **team-based** record visibility |
| **User** | Anyone who buys a licence | A sales team inside an organisation that has bought the CRM entitlement |

**The one-sentence difference:** *Zoho is a CRM construction kit; S3K is a CRM.* Zoho's
configurability exists because Zoho cannot know its customer. S3K can. Every recommendation in
Phase 5 that would import Zoho's configurability machinery has to justify itself against that.

---

## 4.2 What S3K already does well — do not discard

These are strengths found in the code, several of which are **better than the Zoho behaviour they
correspond to**. They are listed because the temptation when benchmarking against a market leader
is to replace things that are already right.

### 1. Tenant isolation is enforced by construction, not by discipline

`backend/app/products/crm/common.py` defines `CrmEntityMixin`, which every CRM model inherits,
supplying `organization_id` among the standard columns. The comment states the intent: it "makes
it impossible to create a CRM table that accidentally omits `organization_id` and therefore
escapes RLS."

Better still, `RLS_EXEMPT_TABLES` **inverts the default**: the schema audit discovers
tenant-scoped tables from the database rather than from a list, so any table *without*
`organization_id` is a build failure unless someone has written down why. There is exactly one
entry (`meetings`), with a four-line justification.

`[S3K-specific adaptation — keep]` Zoho has no equivalent because tenancy is invisible to its
users. This is a platform requirement S3K has solved well.

### 2. Lead conversion is atomic, dedup-aware, and audited — and beats Zoho on three counts

`backend/app/products/crm/leads/service.py::LeadService.convert` creates Account + Contact +
optional Opportunity in one transaction. Comparing directly against Phase 2's Zoho findings:

| Behaviour | Zoho | S3K |
|---|---|---|
| Match existing records before creating | Yes, user chooses "add to existing" or "create new" | Yes — `_resolve_account` / `_resolve_contact` reuse an exact name / email / phone match **automatically**, so conversion "never silently duplicates" |
| Phone matching | Unique-field equality | **Digit-normalised, last-10-digit suffix match** — formatting differences still hit |
| Provenance after conversion | Lead is converted; the link back is not a structured field set | **`converted_account_id`, `converted_contact_id`, `converted_opportunity_id`, `converted_at` are persisted on the lead** |
| One audit event tying the records together | Not documented | **`AuditAction.LEAD_CONVERTED`** with all three child ids in `details`, written precisely because "the generic CREATED entries for those do not say what caused them" |
| Reaching CONVERTED by editing a status field | Possible in principle | **Impossible.** `CONVERTED` is absent from every source list in `LEAD_TRANSITIONS`, so it is reachable only through `convert()` |

`[CRM best practice — keep and build on]` The last row is the strongest single design decision in
the CRM codebase.

### 3. The lead lifecycle is data, not branching

`LEAD_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]]` encodes the legal moves, with the
stated reason: "Encoding it as data rather than as branching keeps it inspectable and testable."
`change_status` rejects an illegal move with `InvalidLeadTransitionError` and returns the allowed
set in `details`.

This is a **lightweight Blueprint** (Phase 2 §5) — preventive process control rather than
reactive automation — and Zoho only offers it on paid tiers with a `Manage Automation` permission.
`[CRM best practice — keep]`

### 4. Pipeline modelling is more correct than Zoho's in two places

- `PipelineStage.is_won` / `is_lost` are booleans with a `CheckConstraint("NOT (is_won AND
  is_lost)")`. The docstring gives the reason: "Deriving closure from flags rather than from the
  stage's name keeps the business rule intact when a tenant renames 'Closed Won'." Zoho's
  equivalent depends on stage configuration.
- `OpportunityStageHistory` is an **append-only** table (no soft delete, no `updated_by`) that
  records every stage change — "which is what makes velocity and conversion reporting possible
  later." Zoho surfaces velocity through reports and Zia; S3K owns the raw data.

`[CRM best practice — keep]`

### 5. Soft delete does not burn unique names

`lead_sources`, `pipelines` and `pipeline_stages` all use **partial unique indexes** with
`postgresql_where=text("deleted_at IS NULL")`. The `LeadSource` comment records the bug this
fixed: an unconditional constraint "meant archiving a name burned it forever — and because the
service's own duplicate check already excluded archived rows, the INSERT sailed past it and
failed in the database as a 500 instead of a 409."

`[CRM best practice — keep]` This is exactly the class of bug that a Zoho-style "just add a
unique field" recommendation would reintroduce.

### 6. Search is a considered design, not a `LIKE` query

`searchable()` in `common.py` builds `Computed(..., persisted=True)` tsvector columns, deferred so
list endpoints do not ship kilobytes of lexemes per row. The weighting decisions are argued in
comments and are genuinely thoughtful:

- `EMAIL_TERMS` splits an address into the whole string, the local part and the **first domain
  label** — so "find everyone at Zephyr" works, while deliberately not indexing the TLD because
  "com" would become a lexeme matching most of the database.
- `Lead.company` sits at weight `B`, not `A`, so searching "Acme" surfaces the *account* above the
  four leads who work there.
- `Opportunity`'s vector deliberately **excludes** account and contact names: "Copying them would
  mean every rename of an account silently rewriting the vectors of its deals, and a stale copy is
  worse than a join."

That last one is the Phase 2 copy-vs-link discipline applied correctly, unprompted.
`[CRM best practice — keep]`

### 7. Record-level visibility is centralised and fails safe

`shared/visibility.py` implements three widening rungs — `VIEW_ALL` → `VIEW_TEAM` → owner-only
plus unowned rows — applied **inside `TenantScopedRepository`**, "at the single point every read
of a CRM table goes through, so a new endpoint cannot forget it." A `VIEW_TEAM` holder on no team
falls back to owner-only, explicitly "the safe direction: an empty peer set must never read as
'no restriction'."

This is the same shape as Zoho's role hierarchy + sharing rules, at a fraction of the complexity,
and correctly separated from tenant isolation. `[S3K-specific adaptation — keep]`

### 8. The UI refuses to fake data

`frontend/app/(crm)/qualification/page.tsx` carries a comment explaining that BANT/MEDDICC
scoring is deliberately absent because `QualificationRecord` does not exist yet: "The previous
version of this page displayed five invented leads with invented scores; a queue that lies about
who is qualified is worse than an empty one."

`[Keep]` — this norm matters more than any feature in this document.

---

## 4.3 What S3K has today — the honest inventory

**Backend CRM modules** (`backend/app/products/crm/`): `accounts`, `contacts`, `leads`
(+ `lead_sources`), `opportunities` (+ `pipelines`, `pipeline_stages`,
`opportunity_stage_history`), `campaigns` (+ `campaign_members`), `activities` (+ `meetings`),
`tasks`, `notes`, `dashboard`, `search`, `shared`.

**Platform modules**: `auth`, `authorization`, `organizations`, `teams`, `documents`, `audit`,
`notifications`, `products` (entitlements).

**API surface** — every CRM module exposes the same five REST operations, plus these
domain-specific ones:

| Endpoint | Significance |
|---|---|
| `POST /leads/{id}/convert` | The atomic conversion |
| `GET /leads/{id}/conversion-suggestions` | Pre-flight match list for the convert UI |
| `POST /leads/{id}/status`, `POST /leads/{id}/owner` | State machine and ownership as explicit operations, not field edits |
| `GET /leads/status-counts`, `GET /tasks/status-counts` | Kanban column headers |
| `POST /opportunities/{id}/stage`, `/reopen`, `GET /{id}/history` | Stage machine + stage history |
| `GET /activities/timeline` | Cross-entity activity feed |
| `POST /contacts/{id}/primary` | Set the account's primary contact |
| `GET /search` | Cross-module search |
| `GET /dashboard/summary` | KPIs |

**Frontend routes**: dashboard, lead-sources, leads, qualification, campaigns, meetings,
accounts, contacts, opportunities, tasks, admin (users / roles / teams / audit-logs / security /
integrations / crm-settings), and a large `ai` + `ai-settings` console.

### Gaps visible from the code (detailed in Phase 5)

- **No import, export, or bulk endpoints anywhere.** A search across `backend/app` for
  bulk/import/CSV/export finds only Python `import` statements and pagination helpers.
- **No products, quotes, orders or invoices** — `Opportunity.products` and `Campaign.products`
  are plain `Text` columns, not relationships to a catalogue.
- **No `QualificationRecord`** — the frontend page says so itself.
- **No automation engine** — no workflow rules, no assignment rules, no scoring rules, no
  scheduler. `Lead.ai_score` and `Contact.ai_score` are marked "Persisted only; nothing computes
  it yet."; `Campaign.leads_generated` / `opportunities_generated` / `conversion_rate` / `roi` are
  "Maintained by background aggregation" — a job runner that is not present in this module.
- **No duplicate management beyond leads** — `create_lead` checks for an open duplicate email
  (`DuplicateLeadEmailError`, overridable with `allow_duplicate`); Accounts and Contacts have no
  equivalent guard on their create paths.
- **AI console pages exist in the frontend with no CRM backend behind them** on this branch.

---

## 4.4 What Zoho complexity is out of scope for S3K

`[Intentionally not adopted]` — with the reason in each case.

| Zoho capability | Why it is out of scope for S3K CRM |
|---|---|
| **Quotes, Sales Orders, Invoices, Purchase Orders, Price Books** | `03-S3K-CRM-ARCHITECTURE.md` assigns accounting, invoicing and payments to **S3K Books**. Building them in CRM would violate the product boundary the whole modular monolith exists to protect. A *link* to a Books document is in scope later; the documents themselves are not |
| **Cases / Solutions (helpdesk)** | Explicitly assigned to **S3K Support** |
| **Vendors / Purchase side** | Procurement is not in the CRM boundary, and no sibling product claims it yet |
| **Contracts & e-signature** | **S3K Contracts** |
| **Custom modules, custom fields, Canvas designer** | S3K is a product with a fixed model, not a construction kit (§4.1). Native PostgreSQL enums and typed SQLAlchemy columns are a deliberate bet on knowing the domain |
| **Page layouts per profile, conditional layouts** | Same reason. A *small* amount of conditional form behaviour is worth having (Phase 5); a layout engine is not |
| **Territories, data sharing rules, role hierarchy** | Team-based visibility (§4.2.7) already covers the realistic cases at far lower cost. Revisit only if a customer actually needs geography-based access |
| **Zoho's arbitrary limits** — 2 unique fields/module, 5 alerts, 3 field updates, 5–10 scoring rules, 1 escalation rule | These are multi-tenant SaaS metering artefacts, not design wisdom. A single-purpose product should not inherit a ceiling it does not need |
| **Forecasts as a separate module** | S3K has `expected_close_date`, `deal_value`, `win_probability`, `forecast_category` and an append-only stage history. Forecasting should be a **query**, not a table of manually maintained quotas |
| **Web-to-Lead public forms** | Not out of scope forever, but they carry a public unauthenticated write path, spam surface and CAPTCHA problem (which Zoho itself has not solved well). Sequence them behind the internal essentials |
| **Solutions / knowledge base** | Belongs with Support |

---

## 4.5 Where S3K's model and stack constrain porting a Zoho pattern

These are the real engineering constraints Phase 5 must design around. Each is a fact about the
code, not a preference.

### C1 — Polymorphic relations are validated in the service layer, not by foreign keys

`Activity`, `Task` and `Note` all carry `related_entity_type` (a `CrmEntityType` enum of
`ACCOUNT`, `CONTACT`, `LEAD`, `OPPORTUNITY`, `CAMPAIGN`) plus a bare `related_entity_id` UUID.
`common.py` states why: "one column cannot reference five tables", and every write path checks the
target exists within the caller's organization.

**Consequences.** No referential integrity and no database cascade — deleting an Account cannot
automatically remove its activities the way Zoho's cascade delete does. Any "related list" or
"open/closed activities" work must go through the service layer. Adding a sixth relatable entity
requires a PostgreSQL enum migration.

### C2 — `owner_id` is deliberately not a foreign key

Every CRM model comments: "Platform user id. Not a foreign key: ownership must survive the owner
leaving the platform, and CRM tables do not depend on platform tables."

**Consequences.** This is the right call for module boundaries, but it means round-robin
assignment, "reassign everything when a user is deactivated", and owner-name search all need a
**cross-module query or event**, not a join. Zoho's Mass Transfer has no cheap equivalent here.

### C3 — No background job runner in the CRM module

`Campaign`'s cached metrics say "Maintained by background aggregation, never by request
handlers", but no such worker exists in `backend/app/products/crm/`. Redis is in
`docker-compose.yml` and the README names it for "jobs, cache, files".

**Consequences.** Every Zoho **time-based** automation — follow-up reminders, escalation,
rollup refresh, score decay, "no activity in 14 days" — has nowhere to run today. This is the
single largest structural gap between S3K and the Zoho automation catalogue, and it is
infrastructure, not features.

### C4 — Generated `search_vector` columns constrain bulk writes

The tsvector columns are `Computed(..., persisted=True)`, so PostgreSQL recomputes them on every
insert and update. That is correct for interactive use, and it is a cost to plan for when a bulk
importer arrives (Phase 5) — a 30,000-row import is 30,000 tsvector computations plus RLS
predicates.

### C5 — Native enums make picklists a migration, not a setting

`LeadStatus`, `AccountStatus`, `CampaignType`, `TaskStatus`, `Priority` and the rest are
`native_enum=True` PostgreSQL types. Adding a value is an Alembic migration.

**Consequence.** Zoho's "let the customer add a picklist value" is not portable as-is. Where a
list genuinely needs to be tenant-editable, it must become a table — `lead_sources` is already
exactly that, and it is the correct precedent to follow (pipelines/stages likewise).

### C6 — Products are free text

`Opportunity.products` and `Campaign.products` are `Text`. There is no catalogue entity.

**Consequence.** Anything resembling Zoho's line items, price books, or product-based reporting
requires a new module first. Note that `Lead.product_interest` is already carried into
`Opportunity.products` on conversion — the flow exists, the entity does not.

### C7 — `Contact.account_id` is nullable; `Opportunity.account_id` is `RESTRICT`

Contacts may be orphans (matching Zoho); opportunities may not, and their account cannot be
deleted out from under them (`ondelete="RESTRICT"`). Any "create an opportunity from a contact"
flow must resolve or create an Account first.

### C8 — Lead statuses and pipeline stages model overlapping reality

`LeadStatus` includes `PROPOSAL_SENT` and `NEGOTIATION`, and `CONVERTIBLE_FROM` allows conversion
from `QUALIFIED`, `PROPOSAL_SENT` or `NEGOTIATION`. So a lead can reach "Negotiation" **without an
Opportunity existing** — meaning pipeline state lives in two places, and a deal in negotiation may
have no `deal_value`, no `expected_close_date`, no stage history and no presence in any forecast.

In Zoho this cannot happen: negotiation is a Deal stage, and Deals only exist post-conversion.
**This is a genuine design tension in S3K's model, not a missing feature**, and Phase 5 addresses
it explicitly.

---

## 4.6 Where S3K should intentionally diverge from Zoho

`[S3K-specific adaptation]` in each case.

| Divergence | Decision | Why |
|---|---|---|
| **"Opportunity", not "Deal"** | Keep S3K's naming | Already consistent across models, routes, permissions and the frontend. Zoho itself uses three names for this ("Deals", "Potentials", "Opportunities"); consistency beats matching a competitor's label |
| **"Lead Source" is an entity, not a picklist** | Keep and extend | `crm.lead_sources` is a real table with its own CRUD, status and category. Zoho's Lead Source is a picklist, which is why Zoho cannot report on source cost or lifecycle. S3K's version is **better** and should become the attribution spine |
| **Qualification as an explicit stage** | Keep and complete | Zoho has no qualification model — it has a Rating picklist and Zia scoring. S3K's route, plus the planned `QualificationRecord` (BANT/MEDDICC), is a real differentiator for a considered B2B sale |
| **Conversion auto-reuses matches instead of prompting** | Keep, but surface it | Zoho asks the user; S3K decides. Given `GET /conversion-suggestions` already exists to show matches beforehand, S3K's behaviour is defensible — but the *response* must make clear which records were reused rather than created |
| **`is_won`/`is_lost` flags over stage names** | Keep | Survives renames |
| **Ownership + teams instead of role hierarchy + sharing rules** | Keep | Covers the realistic cases at a fraction of the complexity |
| **Process order: no Quote/Order/Invoice tail** | Diverge deliberately | Zoho's canonical order ends `… → Quote → Sales Order → Invoice`. S3K's ends at opportunity closure, then hands off to Books. The creation order in Phase 5 reflects this |
| **Lead status vs. opportunity stage** | Diverge from the current S3K model | See C8 — recommend shortening the lead lifecycle so post-qualification selling happens on the Opportunity, where the pipeline machinery already lives |

---

## 4.7 The S3K creation order (superseding Zoho's)

Zoho's implied order is Account → Contact → Deal → Activities → Quote → Sales Order → Invoice.
Adjusted for §4.4 (no commercial documents) and §4.6 (qualification is real, lead sources are
entities), S3K's is:

```
SETUP (once, per organization)
  Organization → Users → Roles → Teams → Product entitlement
  Pipeline → Pipeline Stages          (an opportunity cannot exist without a stage)
  Lead Sources                        (attribution spine)

OPERATE (per customer journey)
  Campaign (optional)
      ↓  membership
  Lead  ──▶ Qualification ──▶ CONVERT ──┬──▶ Account
                                        ├──▶ Contact
                                        └──▶ Opportunity
                                                 ↓  stage progression + history
                                          Activities / Tasks / Notes / Meetings
                                                 ↓
                                          Closed Won / Closed Lost
                                                 ↓
                                          hand-off to S3K Books (out of scope)
```

Two ordering facts fall out of the code and must be respected:

1. **A pipeline with at least one open stage must exist before any conversion can create an
   opportunity.** `_create_opportunity` raises `ValidationFailedError` — "No pipeline stage is
   configured for this organization" — otherwise. Organization setup therefore has a hard
   prerequisite that first-run onboarding must satisfy.
2. **An Account is created before the Contact, and the Contact before the Opportunity**, because
   `Opportunity.account_id` is `NOT NULL` with `ondelete="RESTRICT"`. `convert()` already does
   this in the right order and sets `account.primary_contact_id` if it was empty.

---

## 4.8 What Phase 4 establishes for Phase 5

1. **The product is a bounded CRM inside a platform**, not a Zoho competitor. Roughly half of
   Zoho's module surface is *someone else's product* by explicit architectural decision.
2. **The existing core is strong.** Conversion, the lead state machine, stage history, visibility,
   search weighting and soft-delete-aware uniqueness are all done well and in several places
   better than Zoho. Phase 5 extends; it does not rewrite.
3. **The largest structural gap is infrastructure, not features** — there is no scheduler, so no
   time-based automation of any kind is possible yet (C3).
4. **The largest functional gap is bulk data** — no import, no export, no bulk operations
   anywhere. This is the difference between a demo and a system a team can move onto.
5. **The largest modelling question is C8** — lead status and pipeline stage currently model the
   same reality twice.
6. **`lead_sources` is the template** for anything that needs to be tenant-configurable without a
   layout engine: make it a table, not a picklist, not a custom-field system.

---

# Phase 5 — S3K blueprint and gap analysis

Phases 1–3 are the reference; Phase 4 is the constraint set. Phase 5 is the target design, and an
honest audit of the distance to it.

## 5.1 Module-by-module blueprint

Each module below states its purpose, its required and optional fields, its relationships, its
creation and import flows, the automations it should carry, its data dependencies, and — the
point of the whole exercise — **the manual work that should be eliminated**.

Tags: `[Z]` Zoho does this · `[BP]` CRM best practice · `[S3K]` S3K-specific adaptation ·
`[NO]` intentionally not adopted.

---

### Lead Sources

| | |
|---|---|
| **Purpose** | The attribution spine. Where prospects come from, as a first-class record rather than a picklist value |
| **Required** | `name` |
| **Optional** | `category`, `description`, `status` (ACTIVE/INACTIVE) |
| **Should add** | `cost_to_date` `[S3K]`, `channel` enum `[S3K]` — so cost-per-lead and ROI become queries rather than spreadsheets |
| **Relationships** | Referenced by `leads.lead_source_id`, `opportunities.lead_source_id`, `campaigns.lead_source_id` (all `SET NULL`) |
| **Creation** | Admin setup, once. Seeded on organization creation `[BP]` |
| **Import** | Rarely needed; support it for parity |
| **Automations** | None needed |
| **Dependencies** | None — this is a root node |
| **Manual work to eliminate** | Typing a source name onto every lead. Already solved by making it an entity — **retain and lean on this**; it is better than Zoho's picklist |

---

### Campaigns

| | |
|---|---|
| **Purpose** | Marketing spend container and the ROI denominator |
| **Required** | `name`, `type` |
| **Optional** | `status`, `owner_id`, `start_date`, `end_date`, `budget`, `expected_revenue`, `target_audience`, `lead_source_id`, `products`, `notes` |
| **Derived (never typed)** | `leads_generated`, `opportunities_generated`, `conversion_rate`, `roi` — already columns; **nothing computes them** |
| **Relationships** | `campaign_members` join (LEAD/CONTACT, unique per campaign+entity); `leads.campaign_id` |
| **Creation** | Manual. Quick Create from a lead's "add to campaign" `[Z]` |
| **Import** | Campaign members by email or record id `[Z]` |
| **Automations** | Recompute cached metrics on lead/opportunity change or on a schedule `[Z rollup]`; close campaigns past `end_date` `[BP]` |
| **Dependencies** | Lead Sources (optional) |
| **Manual work to eliminate** | Counting campaign results by hand. **`Campaign.roi` exists and is always null** — the highest-value/lowest-effort automation in the product, because the data is already there |
| **Gap vs Zoho** | Zoho's `CampaignMember` carries a **Member Status** ("Invited", "Attended"). S3K's `CampaignMember` has only `added_at` — so "who actually attended the webinar" cannot be recorded `[Z — adopt]` |

---

### Leads

| | |
|---|---|
| **Purpose** | Unqualified prospect; the staging area before the permanent database |
| **Required** | `first_name`, `last_name` |
| **Optional** | `company`, `email`, `phone`, `lead_source_id`, `campaign_id`, `owner_id`, `status`, `priority`, `expected_deal_size`, `industry`, `website`, `company_size`, `product_interest`, `notes`, `lost_reason` |
| **Derived** | `ai_score` (column exists, nothing computes it), `search_vector`, `full_name`, `is_converted`, all four `converted_*` fields |
| **Relationships** | → `lead_sources`, `campaigns`; ← `activities`, `tasks`, `notes` (polymorphic); → `accounts`/`contacts`/`opportunities` after conversion |
| **Creation** | Manual, Quick Create from a campaign `[Z]`, import `[Z — missing]`, API |
| **Import** | Match on **email**; add / update / both; "don't update empty values"; assignment rule on import `[Z — missing entirely]` |
| **Automations** | Assignment on create `[Z]`; scoring `[Z]`; "no activity in N days" nudge `[BP]`; auto-`UNQUALIFIED` after N days untouched `[BP]` |
| **Dependencies** | Lead Sources, Campaigns (both optional) |
| **Manual work to eliminate** | Picking an owner by hand on every lead; re-typing company details that conversion will need; manually deciding which leads to work today (that is what a score is for) |
| **Divergence** | Shorten the status set — see §5.7 |

**Note on required fields.** S3K requires `first_name` **and** `last_name`; Zoho requires only
Last Name plus Company. S3K's `company` is nullable, and `_resolve_account` falls back to the
person's full name when it is empty — which quietly creates an Account named after a person.
`[BP]` Either require `company`, as Zoho does, or make that fallback explicit in the UI.

---

### Accounts

| | |
|---|---|
| **Purpose** | The canonical company record and the aggregation point. ADR-008: there is no separate Customer table |
| **Required** | `name` |
| **Optional** | `industry`, `website`, `company_size`, `annual_revenue`, `status`, `owner_id`, `primary_contact_id`, `source`, `description`, address block, `external_id`, `integration_id` |
| **Derived** | `health_score` (column exists, nothing computes it), `search_vector` |
| **Should add** | `parent_account_id` self-FK `[Z]` for company hierarchies; **a separate shipping/billing address pair** if Books integration ever needs it `[Z — defer]` |
| **Relationships** | ← `contacts.account_id` (SET NULL), ← `opportunities.account_id` (**RESTRICT**), ← polymorphic activities/tasks/notes |
| **Creation** | Manual; **auto-created by lead conversion**; import `[missing]` |
| **Import** | Match on `name` (case-insensitive, live rows only) `[Z]` |
| **Automations** | Health score from activity recency + open opportunities + won history `[Z]`; roll up open pipeline value `[Z]` |
| **Dependencies** | None — root node |
| **Manual work to eliminate** | **This is the enter-once hub.** Address, industry, website and company size typed here should populate every downstream form. Today only conversion does this |
| **Duplicate guard** | **Missing.** `LeadService.create_lead` guards duplicate emails; `AccountService` has no name guard, so two "Acme Corp" records can be created freely — and then conversion's `_find_accounts_by_name` will silently pick `[0]` |

---

### Contacts

| | |
|---|---|
| **Purpose** | A person, optionally attached to an account |
| **Required** | `first_name`, `last_name` |
| **Optional** | `account_id`, `email`, `phone`, `mobile`, `job_title`, `department`, `owner_id`, `reporting_manager_id`, `status`, `preferred_communication`, `linkedin_url`, `notes`, address block |
| **Derived** | `ai_score` (uncomputed), `search_vector`, `full_name` |
| **Relationships** | → `accounts` (nullable, SET NULL); ← `opportunities.primary_contact_id`; ← polymorphic activities/tasks/notes; ← `campaign_members` |
| **Creation** | Manual; Quick Create **from an Account's related list, with `account_id` pre-filled** `[Z — the key pattern]`; auto-created by conversion; import `[missing]` |
| **Import** | Match on `email` `[Z]` |
| **Automations** | Inherit the account's owner when created from an account `[BP]`; inherit the account's address unless overridden `[S3K — see §5.4]` |
| **Dependencies** | Accounts (optional) |
| **Manual work to eliminate** | Re-typing the company address on every contact at the same company. Contacts carry a **full address block that duplicates the account's** — this is the clearest enter-twice problem in the current schema |

---

### Opportunities (+ Pipelines, Stages, Stage History)

| | |
|---|---|
| **Purpose** | The unit of forecasting. A quantified deal moving through a pipeline |
| **Required** | `name`, `account_id`, `stage_id` |
| **Should be required** | `expected_close_date` `[Z]` — Zoho mandates Closing Date because a deal with no date cannot enter a forecast. S3K leaves it nullable, and conversion may create an opportunity without one |
| **Optional** | `primary_contact_id`, `owner_id`, `deal_value`, `currency`, `win_probability`, `health_score`, `forecast_category`, `competitor`, `lead_source_id`, `products`, `notes`, `won_at`/`lost_at`/`win_reason`/`loss_reason` |
| **Derived — should be, currently is not** | `win_probability` from `PipelineStage.default_probability` `[Z]`; **expected revenue** = `deal_value × win_probability` `[Z]`; `forecast_category` from stage + probability `[BP]` |
| **Relationships** | → `accounts` (RESTRICT), → `contacts` (SET NULL), → `pipeline_stages` (RESTRICT), → `lead_sources`; ← `opportunity_stage_history` (CASCADE, append-only) |
| **Creation** | Manual; **from an Account or Contact related list** `[Z]`; by conversion; import `[missing]` |
| **Automations** | Set `win_probability` from the stage on every stage change `[Z]`; stamp `won_at`/`lost_at` on terminal stages `[BP]`; require `loss_reason` when moving to a lost stage `[Z Blueprint]`; stale-deal alert `[Z]` |
| **Dependencies** | **Accounts (hard), Pipeline + at least one open stage (hard)** |
| **Manual work to eliminate** | Typing a probability that the stage already implies; recomputing weighted pipeline in a spreadsheet; remembering which deals have gone quiet |

`PipelineStage.default_probability` **exists and is never applied** to `Opportunity.win_probability`.
That is Zoho's single most-copied derivation (Phase 1 §Deals) and the wiring is a few lines.

---

### Activities (Calls / Emails / Meetings / Notes / Tasks) and Tasks

| | |
|---|---|
| **Purpose** | The interaction record |
| **Activity required** | `type`, `subject` |
| **Activity optional** | `description`, `status`, `due_date`, `completed_at`, `outcome`, `owner_id`, `related_entity_type` + `related_entity_id` |
| **Meeting required** | `activity_id`, `meeting_type`, `start_time` |
| **Meeting optional** | `end_time`, `location`, `meeting_link`, `agenda`, `reminder_minutes`, `internal_participant_ids` |
| **Task required** | `title` |
| **Task optional** | `description`, `status`, `priority`, `due_date`, `completed_at`, `owner_id`, `assigned_to_id`, related entity |
| **Creation** | Manual; **Quick Create from any parent record with the relation pre-filled** `[Z]`; auto-created by automation `[Z — missing]` |
| **Automations** | **Meetings should auto-complete when `end_time` passes** `[Z]` — Zoho's documented behaviour, and S3K has `end_time` already; stamp `completed_at` when status → COMPLETED `[BP]`; reminders from `reminder_minutes` `[Z — needs C3]`; overdue-task nudge `[BP]` |
| **Dependencies** | Any of the five `CrmEntityType` targets (optional) |
| **Manual work to eliminate** | Marking meetings done after the fact; re-selecting the related record; chasing overdue items by eye |
| **Gap** | No **open vs. closed activities** split on parent records `[Z]`, and no next-activity summary on Account/Opportunity |

**A modelling wrinkle to resolve.** `ActivityType` includes `TASK` and `NOTE`, but `tasks` and
`notes` are also their own tables. Two ways to record a task therefore exist. Zoho's split is
cleaner: separate modules, and no overlapping type value. `[BP]` Drop `TASK` and `NOTE` from
`ActivityType`, or document the rule.

---

### Notes

| | |
|---|---|
| **Purpose** | Unstructured context, timestamped and attributed |
| **Required** | body, `related_entity_type` + `related_entity_id` |
| **Creation** | Inline from any parent record `[Z]` |
| **Automations** | On conversion, **carry lead notes to the new Account/Contact/Opportunity** `[Z]` — Zoho moves them to the deal and copies to account and contact. S3K currently copies `Lead.notes` (a text column) into `Contact.notes` and `Opportunity.notes`, but any `Note` **records** attached to the lead are left behind |
| **Manual work to eliminate** | Re-reading the lead to find out what was discussed before conversion |

---

### Users, Roles, Teams (platform)

| | |
|---|---|
| **Purpose** | Who may see and do what |
| **Model** | `module.ACTION` permission catalogue; system roles Admin (wildcard) / Manager / User; teams and departments; `VIEW_ALL` and `VIEW_TEAM` as explicit actions |
| **Automations to add** | Round-robin / criteria-based **assignment** `[Z]`; **reassign a deactivated user's records** `[Z Mass Transfer]` |
| **Dependencies** | Organization, product entitlement |
| **Manual work to eliminate** | Hand-picking an owner for every new record; hand-reassigning a departing rep's book of business |
| **Constraint** | `owner_id` is not a FK (C2), so both of these are cross-module operations |

---

### Qualification `[S3K — differentiator]`

| | |
|---|---|
| **Purpose** | A structured, auditable answer to "is this worth pursuing?" — Zoho has no equivalent |
| **Status** | Frontend route exists as a **view over leads**; `QualificationRecord` is not built, and the page says so rather than faking scores |
| **Proposed required** | `lead_id`, `framework` (BANT / MEDDICC), `assessed_by_id`, `assessed_at` |
| **Proposed optional** | Per-criterion score + evidence note; computed total |
| **Derived** | Total score; a suggested `LeadStatus` transition |
| **Automations** | Score ≥ threshold → suggest QUALIFIED `[S3K]`; feed `Lead.ai_score` `[S3K]`; block conversion without a qualification record, if the organization opts in `[Z Blueprint-style]` |
| **Manual work to eliminate** | Qualification currently living in reps' heads and in note text, where it cannot be reported on or coached against |

---

## 5.2 Module dependency map (target state)

```
        ┌──────────────────── PLATFORM ────────────────────┐
        │ Organization → Users → Roles → Teams             │
        │                 ↓ entitlement                    │
        └────────────────────┬─────────────────────────────┘
                             ▼
   SETUP (hard prerequisites, seeded at org creation)
        Lead Sources          Pipeline ──▶ Pipeline Stages
             │                                  │
             │                                  │ RESTRICT
   OPERATE   ▼                                  ▼
        Campaign ──membership──▶  Lead ──▶ Qualification
                                   │
                                   │ CONVERT (atomic, one transaction)
                     ┌─────────────┼─────────────┐
                     ▼             ▼             ▼
                 Account ◀──── Contact      Opportunity
                     ▲  RESTRICT   ▲             │
                     └─────────────┴─────────────┘
                                   │
                        polymorphic related_entity
                                   ▼
                  Activities · Tasks · Notes · Meetings
                                   │
                                   ▼
                        Closed Won / Closed Lost
                                   │
                                   ▼
                     [ hand-off to S3K Books — out of scope ]
```

**Hard dependencies (cannot create without):** Opportunity → Account; Opportunity →
PipelineStage; PipelineStage → Pipeline; CampaignMember → Campaign; Meeting → Activity;
StageHistory → Opportunity.

**Soft dependencies (nullable):** Contact → Account; everything → Lead Source; Lead → Campaign;
Activity/Task/Note → any of five entity types.

**The onboarding consequence.** A brand-new organization with no pipeline **cannot convert a
lead** — `_create_opportunity` raises `ValidationFailedError`. First-run setup must therefore seed
a default pipeline, stages, and lead sources, or the first user hits a wall on their most
important action. `[BP — high priority]`

---

## 5.3 Record lifecycle map

**Lead** (current, from `LEAD_TRANSITIONS`):
```
NEW ──▶ CONTACTED ──▶ QUALIFIED ──▶ PROPOSAL_SENT ──▶ NEGOTIATION
 │           │            │               │               │
 └───────────┴────────────┴───────────────┴───────────────┴──▶ UNQUALIFIED / LOST
                          └──────────── convert() ────────────▶ CONVERTED (terminal)
UNQUALIFIED ──▶ CONTACTED     LOST ──▶ CONTACTED      (re-open)
```
`CONVERTED` is terminal and reachable only via `convert()`. Re-opening from LOST/UNQUALIFIED is
supported. See §5.7 for the recommended change.

**Opportunity:**
```
[first open stage] ──▶ … ──▶ [stage n] ──▶ is_won  → won_at, win_reason
                                        └─▶ is_lost → lost_at, loss_reason
                    every move appends to opportunity_stage_history
                    POST /opportunities/{id}/reopen returns it to an open stage
```

**Activity / Task:** `PLANNED|PENDING → IN_PROGRESS → COMPLETED|CANCELLED`, with `completed_at`
stamped on completion. Meetings should additionally auto-complete on `end_time` `[Z]`.

**Account:** `ACTIVE | ONBOARDING | AT_RISK | CHURNED` — no transition rules today. `AT_RISK`
should be **derived** from activity recency and open-opportunity health, not typed `[S3K]`.

**Every entity:** soft-deleted via `deleted_at`; live-row-only partial unique indexes; no purge
job and **no restore endpoint** — see the Recycle Bin gap in §5.6.

---

## 5.4 Field dependency map — "enter once, use everywhere"

The central question of this brief. Each row is a value a user should type **once**, with
everywhere it should then appear, and the mechanism from Phase 2 §2.4.

| Entered once on | Value | Should flow to | Mechanism | Status |
|---|---|---|---|---|
| Lead | name, email, phone | Contact | COPY at conversion | **Done** |
| Lead | company, industry, website, company_size | Account | COPY at conversion | **Done** |
| Lead | `expected_deal_size` | `Opportunity.deal_value` | COPY at conversion | **Done** |
| Lead | `product_interest` | `Opportunity.products` | COPY at conversion | **Done** |
| Lead | `lead_source_id` | `Opportunity.lead_source_id` | COPY at conversion | **Done** |
| Lead | `owner_id` | Account, Contact, Opportunity owner | COPY at conversion | **Done** |
| **Account** | **address block** | **Contact address** | inherit-on-create, overridable | **Missing** — contacts have their own address block and nothing pre-fills it |
| **Account** | `owner_id` | Contact / Opportunity created from it | inherit-on-create | **Missing** |
| **Account** | `id` | Opportunity created from an Account's related list | LINK, pre-filled | **Missing** (no related-list create) |
| **Account** | `primary_contact_id` | Opportunity `primary_contact_id` default | DERIVE default | **Missing** |
| **PipelineStage** | `default_probability` | `Opportunity.win_probability` | DERIVE on stage change | **Missing — column exists, never applied** |
| **Opportunity** | `deal_value × win_probability` | weighted pipeline / forecast | DERIVE | **Missing** |
| **Opportunity** | stage → terminal | `won_at` / `lost_at` | DERIVE on transition | **Missing** |
| **Lead/Opp** | `lead_source_id` | Campaign attribution and cost-per-lead | DERIVE (aggregate) | **Missing** |
| **Campaign** | membership + outcomes | `leads_generated`, `opportunities_generated`, `conversion_rate`, `roi` | DERIVE (rollup) | **Missing — all four columns exist, all null** |
| **Account** | activity recency + open pipeline | `health_score` | DERIVE | **Missing — column exists** |
| **Lead** | field completeness + engagement | `ai_score` | DERIVE | **Missing — column exists, marked "nothing computes it yet"** |
| **Contact** | engagement | `ai_score` | DERIVE | **Missing — column exists** |
| **Organization** | business hours, currency, fiscal year | reminders, forecasting periods | LINK | **Missing entirely** |
| **Note on a Lead** | note records | Account / Contact / Opportunity | MOVE/COPY at conversion | **Partial** — the `notes` text column copies; `Note` rows do not |

**The single most striking finding of Phase 5:** S3K has **six derived columns that already
exist in the schema and are never computed** — `Lead.ai_score`, `Contact.ai_score`,
`Account.health_score`, and all four Campaign metrics. The data model already anticipated the
automation. Only the computation is missing. That is an unusually cheap set of wins.

---

## 5.5 Automation opportunity list

Ordered by (value ÷ effort). Format matches Phase 2: Trigger → Condition → Action → Result.

| # | Automation | Trigger → Condition → Action → Result | Tag | Needs |
|---|---|---|---|---|
| A1 | **Stage-driven probability** | Opportunity stage changes → always → set `win_probability` from `PipelineStage.default_probability` unless manually overridden → forecast maths becomes real | `[Z]` | — |
| A2 | **Terminal-stage stamping** | Stage change → target `is_won`/`is_lost` → set `won_at`/`lost_at`; require `win_reason`/`loss_reason` → closure data becomes reportable | `[Z Blueprint]` | — |
| A3 | **Campaign rollups** | Lead or Opportunity created/changed → belongs to a campaign → recompute `leads_generated`, `opportunities_generated`, `conversion_rate`, `roi` → marketing ROI without a spreadsheet | `[Z rollup]` | C3 (or synchronous first) |
| A4 | **Owner assignment on create** | Any CRM record created with no owner → matching rule → assign round-robin within a team, else default owner → nothing is ever unassigned | `[Z + S3K]` | C2 |
| A5 | **Meeting auto-complete** | `end_time` passes → status is PLANNED → set COMPLETED + `completed_at` → activity history is truthful without clicks | `[Z]` | C3 |
| A6 | **Conversion note carry-over** | Lead converted → notes exist → move `Note` rows to the Opportunity, copy to Account and Contact | `[Z]` | — |
| A7 | **Account health score** | Nightly, or on activity/opportunity change → derive from recency, open pipeline, won history → `AT_RISK` becomes evidence rather than opinion | `[Z]` | C3 |
| A8 | **Lead scoring** | Field change or engagement → scoring rules → set `ai_score` → reps work the right leads first | `[Z]` | C3 for decay |
| A9 | **Stale-record nudges** | Nightly → lead/opportunity untouched N days → notify owner, flag record | `[Z time-based]` | C3 |
| A10 | **Follow-up task on stage entry** | Opportunity enters a stage → stage has a configured next step → create a Task for the owner | `[Z]` | — |
| A11 | **Deactivated-user reassignment** | Platform user deactivated → owns CRM records → bulk reassign to manager or team, including open activities | `[Z Mass Transfer]` | C2 |
| A12 | **Duplicate guard on Accounts/Contacts** | Create → name/email matches a live record → warn with the match, allow override | `[Z]` | — |
| A13 | **Auto-unqualify dormant leads** | Nightly → NEW/CONTACTED and untouched N days → move to UNQUALIFIED with a system reason | `[BP]` | C3 |
| A14 | **First-run org seeding** | Organization created → no pipeline exists → seed default pipeline, stages, lead sources, roles | `[BP]` | — |
| A15 | **Qualification → status suggestion** | QualificationRecord saved → total ≥ threshold → suggest QUALIFIED | `[S3K]` | Qualification module |

**A1, A2, A6, A10, A12 and A14 need no new infrastructure at all.** A3, A5, A7, A8, A9, A11 and
A13 need the scheduler (constraint C3), which is why it is sequenced early in Phase 6.

## 5.6 Validation strategy

Zoho splits validation across four mechanisms (Phase 2). S3K should adopt the split, not the
implementation, and should place each rule at the layer that can actually enforce it.

| Layer | Enforces | S3K mechanism | State |
|---|---|---|---|
| **Database** | Invariants that must hold no matter what writes the row | `NOT NULL`, FK + `ondelete`, `CheckConstraint`, partial unique indexes, RLS | **Strong already** — score ranges, `NOT (is_won AND is_lost)`, `deal_value >= 0`, `end_date >= start_date` |
| **Schema (Pydantic)** | Shape, type, length, format | Request/response models per module | Present |
| **Service** | Business rules and cross-record consistency | `LEAD_TRANSITIONS`, `CONVERTIBLE_FROM`, `resolve_related_entity`, duplicate guards | Present for leads; thin elsewhere |
| **Process gate** | "You may not do X until Y is true" | Not built | **Missing** — this is Zoho's Blueprint slot |

### Rules to add, by layer

**Database.**
- `CheckConstraint` that `won_at`/`lost_at` are set iff the stage is terminal — or accept that
  this is service-level, since it spans a join.
- Partial unique index on `accounts (organization_id, lower(name)) WHERE deleted_at IS NULL` —
  matching the existing `lead_sources` / `pipelines` precedent, and closing the duplicate-account
  hole that conversion's `matches[0]` currently papers over. `[BP]`
- Partial unique index on `contacts (organization_id, lower(email)) WHERE deleted_at IS NULL AND
  email IS NOT NULL`. `[Z]`

**Service.**
- **Duplicate warnings that are overridable, not fatal.** Follow the existing
  `create_lead(allow_duplicate=...)` pattern for Accounts and Contacts — it is already the right
  shape: a 409 with the matching record, and an explicit opt-out. `[Z + S3K]`
- **Path-dependent duplicate behaviour** `[Z]`: interactive create → 409 with the match;
  import → skip/update per the import's setting; API → hard reject. Same rule, three responses.
- Require `expected_close_date` when an opportunity is created or when it leaves the first stage
  `[Z]`.
- Require `loss_reason` when moving to an `is_lost` stage; `win_reason` on `is_won` `[Z Blueprint]`.
- Validate that `related_entity_id` exists in the caller's organization on **every** polymorphic
  write — already done in activities; confirm parity in tasks and notes (C1).

**Process gates** (the Blueprint slot, S3K-sized).
Do **not** build a general workflow designer `[NO]`. Build a small, declarative table of
stage-entry requirements — the same "data, not branching" approach `LEAD_TRANSITIONS` already
proves works:

```
STAGE_REQUIREMENTS = {
    stage_is_won:  {"win_reason", "deal_value", "expected_close_date"},
    stage_is_lost: {"loss_reason"},
    ...
}
```

This delivers Zoho's Blueprint value — *gate the change before it happens* — at perhaps 5% of
Blueprint's complexity, and stays inspectable and testable.

### Import validation (when the importer lands)

Zoho's failure list (Phase 3 §3.3) is the test plan: missing header row, empty mandatory fields,
encoding, date format, empty rows, and unknown enum values. **Reject unknown enum values rather
than inventing them** `[Z]` — with S3K's native PostgreSQL enums this is not even a choice.
Return a per-row error report; never fail the whole file on one bad row.

### The Recycle Bin gap

Every CRM entity is soft-deleted (`deleted_at`), but there is **no restore endpoint and no purge
job**. Zoho's 60-day Recycle Bin is the model `[Z]`: soft delete without restore is not a safety
net, it is just rows accumulating. Add `POST /{module}/{id}/restore` and a retention job.

---

## 5.7 Resolving C8 — lead status vs. opportunity stage

Flagged in Phase 4 as the one genuine modelling flaw. Stating the recommendation plainly.

**The problem.** `LeadStatus` runs `NEW → CONTACTED → QUALIFIED → PROPOSAL_SENT → NEGOTIATION`,
and `CONVERTIBLE_FROM` permits conversion from any of the last three. So a lead can sit in
NEGOTIATION with no Opportunity — no `deal_value`, no `expected_close_date`, no stage history, and
absent from every pipeline view and forecast. The same commercial reality is modelled in two
places, and the weaker copy is the one that wins by default.

**Recommendation** `[S3K-specific adaptation]`:

```
NEW ──▶ CONTACTED ──▶ QUALIFIED ──convert()──▶ CONVERTED
 └──────────┴─────────────┴──────────────────▶ UNQUALIFIED / LOST
```

Deprecate `PROPOSAL_SENT` and `NEGOTIATION` as *lead* statuses; they are **pipeline stages**,
where `deal_value`, `expected_close_date`, `default_probability` and stage history already exist
to support them. Qualification becomes the single gate: qualify, convert, then sell on the
Opportunity.

**Why this is right rather than merely tidier.** It is Zoho's model — negotiation is a Deal stage,
and Deals exist only post-conversion — arrived at for the same reason: pipeline machinery should
have exactly one home. It also makes forecasting honest, because nothing commercially real can
exist outside the pipeline.

**Migration path.** Keep the enum values for existing rows; remove them from `LEAD_TRANSITIONS`'s
target sets so no new lead can enter them; add `PROPOSAL_SENT`/`NEGOTIATION` to `CONVERTIBLE_FROM`
as legacy-only. Then seed the default pipeline with matching stage names so nothing is lost in
translation.

---

## 5.8 Gap analysis against the actual codebase

Every item is classified against `feat/platform-phase1-crm-core`.

### ✅ Already implemented (do not rebuild)

| Capability | Where |
|---|---|
| Multi-tenant isolation with RLS + enforced-by-mixin `organization_id` | `common.py::CrmEntityMixin`, `RLS_EXEMPT_TABLES` |
| Atomic, dedup-aware, audited lead conversion | `leads/service.py::convert` |
| Lead state machine as data, `CONVERTED` unreachable by edit | `LEAD_TRANSITIONS`, `CONVERTIBLE_FROM` |
| Pipelines, stages, `is_won`/`is_lost` flags, append-only stage history | `opportunities/models.py` |
| Opportunity reopen + history endpoints | `opportunities/router.py` |
| Record-level visibility: VIEW_ALL / VIEW_TEAM / owner, applied in the repository | `shared/visibility.py` |
| RBAC catalogue with `module.ACTION`, system roles, wildcard Admin | `authorization/catalog.py` |
| Teams & departments | `platform/teams` |
| Weighted full-text search across modules, with deferred generated columns | `common.py::searchable`, `crm/search` |
| Audit log with domain-specific actions (`LEAD_CONVERTED`, `LEAD_STATUS_CHANGED`, `OWNER_REASSIGNED`) | `platform/audit` |
| Soft delete + live-row-only partial unique indexes | `lead_sources`, `pipelines`, `pipeline_stages` |
| Campaign membership as a join entity | `campaigns/models.py::CampaignMember` |
| Polymorphic activities/tasks/notes with org-scoped validation | `activities/service.py` |
| Document attachments (MinIO/R2) | `platform/documents` |
| Product entitlements gating CRM access | `platform/products` |
| Duplicate-email guard on lead create, with explicit override | `create_lead(allow_duplicate=...)` |
| Kanban status counts endpoints | `/leads/status-counts`, `/tasks/status-counts` |

### 🟡 Partially implemented

| Capability | What exists | What is missing |
|---|---|---|
| **Campaign ROI** | All four metric columns | Nothing computes them (A3) |
| **Scoring** | `Lead.ai_score`, `Contact.ai_score` columns + range checks | No scoring rules (A8) |
| **Account health** | `health_score` column + range check | No derivation (A7) |
| **Probability** | `PipelineStage.default_probability` | Never applied to the opportunity (A1) |
| **Closure data** | `won_at`, `lost_at`, `win_reason`, `loss_reason` | Not stamped or required on transition (A2) |
| **Qualification** | Frontend queue over real leads | No `QualificationRecord`; BANT/MEDDICC unpersistable |
| **Conversion note carry-over** | `notes` text column copied | `Note` rows left on the lead (A6) |
| **Duplicate management** | Leads only | Accounts, Contacts unguarded (A12); no merge anywhere |
| **Soft delete** | `deleted_at` everywhere | No restore endpoint, no purge job |
| **Meetings** | Full model incl. `end_time`, `reminder_minutes` | No auto-complete (A5), no reminders |
| **Campaign membership** | Join with uniqueness | No **member status** — cannot record "attended" |
| **Activity timeline** | `GET /activities/timeline` | No open/closed split on parent records |

### ❌ Missing entirely

| Capability | Impact |
|---|---|
| **Import (CSV/XLSX) for any module** | Blocks every real customer migration. The single biggest adoption blocker |
| **Export** | `PermissionAction.EXPORT` exists in the catalogue and is granted to Manager — **the permission is defined but nothing implements it** |
| **Bulk operations** — mass update, mass transfer, mass delete | Unusable at real data volumes |
| **Background job runner / scheduler** (C3) | No time-based automation of any kind is possible |
| **Assignment rules** | Every record's owner is whoever typed it |
| **Workflow / automation engine** | No reactive automation at all |
| **Merge duplicates** | No remedy once duplicates exist |
| **Related-list "create child" flows** | The single highest-value UX pattern from Phase 3 |
| **Organization settings** — business hours, currency, fiscal year | Reminders and forecasting have no calendar to work against |
| **Reports** | Named "Not implemented" in the architecture doc |
| **Web-to-Lead** | Deliberately deferred (§4.4) |
| **Notifications delivery** | `platform/notifications` has a module but **no router endpoints** |
| **`Account.parent_account_id`** | No company hierarchies |
| **Email integration / logging** | `ActivityType.EMAIL` exists; nothing produces those rows |

### ⚠️ Poorly designed / should change

| Issue | Why it matters | Recommendation |
|---|---|---|
| **C8 — lead status duplicates pipeline stage** | Commercially real deals can exist outside the pipeline and outside every forecast | §5.7 — shorten the lead lifecycle |
| **`ActivityType` includes `TASK` and `NOTE`** while `tasks`/`notes` are their own tables | Two ways to record the same thing; reporting becomes ambiguous | Remove the overlapping enum values, or document the rule |
| **`Opportunity.expected_close_date` nullable** | A deal with no date cannot enter a forecast; Zoho makes this mandatory for exactly this reason | Require it on create, or on leaving the first stage |
| **`Contact` carries a full address block duplicating `Account`'s** | Guaranteed enter-twice and guaranteed drift | Inherit from the account on create; keep the override |
| **`Opportunity.products` / `Campaign.products` are free text** | No product reporting, no line items, no cross-sell analysis | Accept for now (out of scope, §4.4); revisit when Books lands |
| **Conversion silently picks `matches[0]`** when several accounts share a name | Non-deterministic linkage | Close the duplicate hole at the source (unique index + guard), then this is moot |
| **`_find_contacts_by_phone` loads 50 rows and filters in Python** | Correct today, will not scale, and is unindexable | Store a normalised `phone_digits` generated column and match in SQL |
| **`Lead.company` nullable with a full-name fallback** creating person-named Accounts | Silently pollutes the Account list | Require `company`, or make the fallback visible in the UI |
| **`EXPORT` permission granted but unimplemented** | The permission matrix promises a capability that does not exist | Implement export, or remove the action until it does |

### 🚫 Deliberately not applicable

Quotes · Sales Orders · Invoices · Purchase Orders · Price Books · Products catalogue (→ S3K
Books) · Cases · Solutions (→ S3K Support) · Vendors · Contracts (→ S3K Contracts) · custom
modules · custom fields · Canvas designer · page layouts per profile · conditional layout engine ·
territories · role hierarchy with sharing rules · Forecasts as a stored module · Zoho's numeric
limits · Zia AI features as specified.

Rationale in §4.4. In short: half of Zoho's surface belongs to a sibling product, and most of the
rest is configurability that exists because Zoho cannot know its customer.

---

## 5.9 The manual-work ledger

Answering the brief's central question directly. Each row: what a user types today that they
should not have to.

| Typed today | Should come from | Automation |
|---|---|---|
| Record owner, on every create | Assignment rule / round-robin within team | A4 |
| Win probability, on every stage change | `PipelineStage.default_probability` | A1 |
| Won/lost dates | The terminal stage transition | A2 |
| Campaign lead counts, conversion rate, ROI | Membership + opportunity outcomes | A3 |
| "Which leads should I work today?" | Lead score | A8 |
| "Is this account at risk?" | Health score from activity + pipeline | A7 |
| Marking a finished meeting complete | `end_time` elapsing | A5 |
| Contact address, for every colleague at one company | The Account's address | inherit-on-create |
| The parent record when creating a child | The related list you clicked from | related-list create |
| Re-reading the lead after conversion | Notes carried across | A6 |
| Chasing stale deals by eye | Nightly staleness check | A9 |
| Reassigning a departing rep's records one at a time | Bulk reassignment on deactivation | A11 |
| Re-keying an existing customer list into the CRM | CSV import with mapping and dedup | importer |
| Checking whether a company already exists before creating it | Duplicate guard with match display | A12 |
| Setting up a pipeline before the first conversion can work | Seeded defaults at org creation | A14 |

---

# Phase 6 — Prioritized implementation plan

The final deliverable. No implementation code — this is sequence, rationale and acceptance
criteria.

## 6.0 The three rules that set the order

1. **Unblock the product before enriching it.** A CRM a team cannot move their existing data into
   is a demo. Import outranks scoring.
2. **Build infrastructure exactly once, before the work that needs it.** Seven of the fifteen
   automations require a scheduler (constraint C3). Building it once, early, is cheaper than
   deferring seven features.
3. **Cash the free wins first.** Six derived columns already exist in the schema with range
   constraints and no computation. Wiring them is hours of work for visible product value, and it
   raises confidence for the larger items behind them.

One sequencing consequence worth stating: **fix the model before automating on top of it.** C8
(lead status duplicating pipeline stage) and the missing account-name uniqueness both distort
data that later automations will consume. Correcting them after scoring and rollups exist means
recomputing everything.

---

## 6.1 Stage 0 — Correct the foundations *(do first; small, and everything rests on it)*

**Why first.** These are cheap, they are data-model correctness rather than features, and every
later stage consumes their output. Doing them after the automations means re-deriving scores and
rollups from data that was wrong when it was computed.

| # | Work | Rationale | Tag |
|---|---|---|---|
| 0.1 | **Partial unique index on `accounts (organization_id, lower(name)) WHERE deleted_at IS NULL`**, plus an overridable duplicate guard on Account create mirroring `create_lead(allow_duplicate=...)` | Closes the hole that makes conversion's `matches[0]` non-deterministic. Uses the precedent `lead_sources` already sets | `[Z]` `[BP]` |
| 0.2 | **Same for `contacts` on `lower(email)`** where email is not null | Email is Zoho's canonical Contact unique field, and conversion already matches on it | `[Z]` |
| 0.3 | **Resolve C8** — remove `PROPOSAL_SENT`/`NEGOTIATION` from `LEAD_TRANSITIONS` targets; keep them convertible for legacy rows; seed matching pipeline stages | Stops commercially real deals existing outside the pipeline and outside every forecast (§5.7) | `[S3K]` |
| 0.4 | **Require `expected_close_date`** on opportunity create, or on leaving the first stage | A deal without a date cannot enter a forecast. Zoho mandates it for exactly this reason | `[Z]` |
| 0.5 | **Normalised `phone_digits` generated column on `contacts`**, indexed; rewrite `_find_contacts_by_phone` to match in SQL | Removes a 50-row Python scan from the conversion path before data volume makes it a bug | `[BP]` |
| 0.6 | **Remove `TASK` and `NOTE` from `ActivityType`** (or document the rule) | Two ways to record one thing makes activity reporting ambiguous | `[BP]` |
| 0.7 | **Decide `Lead.company`**: require it, or surface the person-name fallback in the UI | Stops silently creating Accounts named after people | `[Z]` |

**Acceptance:** no two live Accounts share a name in one organization; no lead can enter a
selling status without an Opportunity; every opportunity has a close date; conversion does no
in-Python row scanning.

---

## 6.2 Stage 1 — Free derivations *(no new infrastructure; highest value ÷ effort in the whole plan)*

**Why here.** Every column already exists with its constraint. This is wiring, and it converts
six dead schema fields into live product behaviour.

| # | Work | Automation | Notes |
|---|---|---|---|
| 1.1 | **Stage-driven probability** — set `Opportunity.win_probability` from `PipelineStage.default_probability` on every stage change, unless manually overridden | A1 | Zoho's most-copied derivation. Enables weighted pipeline immediately |
| 1.2 | **Terminal-stage stamping** — set `won_at`/`lost_at` on transition into an `is_won`/`is_lost` stage; require `win_reason`/`loss_reason` | A2 | Uses the `is_won`/`is_lost` flags S3K already models correctly |
| 1.3 | **Weighted pipeline in the dashboard** — `deal_value × win_probability`, by stage and by owner | — | Falls out of 1.1 for free |
| 1.4 | **Conversion note carry-over** — move `Note` rows to the Opportunity, copy to Account and Contact | A6 | Completes conversion; Zoho's documented behaviour |
| 1.5 | **First-run org seeding** — default pipeline + stages, starter lead sources, system roles at organization creation | A14 | Removes the landmine where a new org cannot convert its first lead at all |
| 1.6 | **Follow-up task on stage entry** — optional `next_step` on `PipelineStage` that creates a Task for the owner | A10 | Small, synchronous, and the first taste of automation for users |

**Acceptance:** a rep never types a probability; won/lost dates and reasons are always present on
closed deals; a brand-new organization can convert a lead within a minute of signup.

---

## 6.3 Stage 2 — Bulk data *(the adoption blocker)*

**Why here and not later.** Everything before this is polish on a system nobody can move onto. No
prospective customer migrates a spreadsheet of 4,000 contacts by hand. This is the single largest
functional gap in §5.8, and `PermissionAction.EXPORT` is already promised in the permission
matrix without an implementation behind it.

| # | Work | Design notes |
|---|---|---|
| 2.1 | **CSV/XLSX importer** for Leads, Accounts, Contacts, Opportunities | Follow Phase 3 §3.3 exactly: upload → auto-map headers → choose matching field (record id first, then the module's unique field) → **Add / Update / Both** → **"don't update empty values"** → owner assignment → per-row error report |
| 2.2 | **Per-module default matching fields** | Leads/Contacts = email, Accounts = name, Opportunities = name — mirroring Zoho's defaults, now backed by the Stage 0 unique indexes |
| 2.3 | **Import history + bounded undo** | Zoho's model: record every import, allow "Undo this import", **auto-confirm after 30 days**, and define the cascade (undoing imported Contacts removes the Accounts they created) |
| 2.4 | **Export** for every module | The `EXPORT` permission already exists and is granted to Manager. Implement it or remove the promise |
| 2.5 | **Bulk operations** — mass update, mass owner transfer (including open activities), mass delete | Zoho's 500-record manual cap with a "select all in view" escape hatch is a reasonable model |
| 2.6 | **Restore endpoint + retention job** | Soft delete without restore is not a safety net. `POST /{module}/{id}/restore`, 60-day window `[Z]` |
| 2.7 | **Path-dependent duplicate behaviour** | Interactive → 409 with the match; import → skip/update per setting; API → hard reject |

**Performance note (C4).** Generated `search_vector` columns recompute per row, and RLS
predicates apply to every write. Batch inserts, and load-test at 30,000 rows before promising a
limit.

**Acceptance:** a new customer can migrate leads, accounts, contacts and open opportunities from
CSV, see exactly which rows failed and why, and undo the whole thing within 30 days.

---

## 6.4 Stage 3 — The scheduler *(infrastructure; unblocks seven automations at once)*

**Why here.** Constraint C3: there is no background job runner in the CRM module, yet `Campaign`'s
own docstring says its metrics are "Maintained by background aggregation." Redis is already in
`docker-compose.yml` and the README names it for jobs. Seven of the fifteen automations in §5.5
are blocked on this and on nothing else.

| # | Work |
|---|---|
| 3.1 | Job runner (Redis-backed), with tenant context propagation — **every job must set the RLS organization context**, or it either sees nothing or sees everything |
| 3.2 | Scheduled/recurring job registration, retries, dead-letter, and observability |
| 3.3 | **Organization settings**: business hours, timezone, currency, fiscal year — reminders and escalation have no calendar to work against without these `[Z]` |
| 3.4 | A documented **automation execution order**, S3K's version of Phase 2 §2.6: `assignment → validation → derivation → rollup → notification` |

**Acceptance:** a scheduled job runs per organization with correct tenant context, is observable,
and retries safely. Nothing user-facing ships in this stage — that is the point of naming it
separately rather than smuggling it inside a feature.

---

## 6.5 Stage 4 — Automation on top of the scheduler

| # | Work | Automation | Value |
|---|---|---|---|
| 4.1 | **Campaign rollups** — leads generated, opportunities generated, conversion rate, ROI | A3 | Four dead columns become marketing's core report. Data is already there |
| 4.2 | **Owner assignment rules** — round-robin within a team, criteria-based, default fallback owner | A4 | Applies on **every** creation path, deliberately fixing Zoho's own gap (manual creation bypasses assignment) `[S3K improves on Z]` |
| 4.3 | **Meeting auto-complete** on `end_time` | A5 | Zoho's documented behaviour; `end_time` already exists |
| 4.4 | **Stale-record nudges** — lead or opportunity untouched N days | A9 | The most-requested feature in every sales team |
| 4.5 | **Deactivated-user reassignment**, including open activities | A11 | Cross-module (C2: `owner_id` is not a FK) — needs a platform event |
| 4.6 | **Account health score** from activity recency, open pipeline, won history | A7 | Makes `AT_RISK` evidence rather than opinion |
| 4.7 | **Lead scoring rules** | A8 | Answers "which leads do I work today" |
| 4.8 | **Auto-unqualify dormant leads** with a system reason | A13 | Keeps the working queue honest |

**Sequencing within the stage:** 4.1–4.3 are mechanical and safe. 4.6–4.7 are judgement-based and
should ship behind a per-organization toggle, because a wrong score erodes trust faster than no
score. Make every derived score explain itself — show the inputs, not just the number.

---

## 6.6 Stage 5 — Workflow efficiency UX

**Why after automation.** These remove keystrokes; the earlier stages remove impossibilities. But
this is where daily satisfaction actually lives, and Phase 3 §3.6 identified it as the highest-
leverage UX work in the reference product.

| # | Work | Pattern |
|---|---|---|
| 5.1 | **Related-list create** on Account, Contact, Opportunity, Campaign detail pages — Quick Create with the parent pre-linked | Phase 3's #1 efficiency principle: never navigate away to create a child |
| 5.2 | **Context inheritance on create-from-parent** — Contact from Account inherits address and owner; Opportunity from Account inherits account, primary contact and owner | Closes the biggest remaining enter-twice gap (§5.4) |
| 5.3 | **Open vs. Closed activities** split on every parent record | `[Z]` — "what is outstanding here" without building a filter |
| 5.4 | **Kanban with per-column aggregation** — deal value per stage, not just card counts; drag to change stage | `status-counts` endpoints already exist; add value aggregation `[Z]` |
| 5.5 | **Inline editing** in list and detail views | Removes the open → edit → save → close cycle |
| 5.6 | **Duplicate warning on create** showing the matching record, with an explicit override | A12, backed by the Stage 0 indexes |
| 5.7 | **Conversion result transparency** — state which records were **reused** versus **created** | S3K auto-reuses where Zoho prompts (§4.6); that is defensible only if the outcome is visible |
| 5.8 | **Conditional form behaviour**, narrowly — reveal `loss_reason` when a lost stage is selected, and similar | Zoho's Layout Rules value without a layout engine `[S3K]` |

---

## 6.7 Stage 6 — S3K's differentiators

Only after the fundamentals. These are what make S3K worth choosing over Zoho rather than merely
comparable to it.

| # | Work | Why it differentiates |
|---|---|---|
| 6.1 | **`QualificationRecord`** — BANT/MEDDICC, per-criterion scores with evidence, `assessed_by`, `assessed_at` | Zoho has no qualification model at all. This is the clearest product differentiator, and the frontend route is already waiting for it |
| 6.2 | **Qualification gates conversion** (per-organization opt-in) | Blueprint-style process control, S3K-sized — using the declarative `STAGE_REQUIREMENTS` approach from §5.6 rather than a workflow designer |
| 6.3 | **Lead-source cost tracking** → cost-per-lead and cost-per-won-deal | `lead_sources` is already an entity rather than a picklist — Zoho *cannot* report this. Lean on the advantage |
| 6.4 | **Campaign member status** (Invited / Attended / Responded) | The one clear thing Zoho's join model has that S3K's does not `[Z]` |
| 6.5 | **Reports** | Named "Not implemented" in the architecture doc. Stage history and lead sources make pipeline velocity and source ROI genuinely answerable |
| 6.6 | **Books hand-off** — a link from a won Opportunity to a Books quote/invoice | Honours the product boundary (§4.4) instead of rebuilding invoicing inside CRM |

---

## 6.8 Deferred, with reasons

| Item | Why deferred, not dropped |
|---|---|
| **Web-to-Lead forms** | Public unauthenticated write path, spam surface, CAPTCHA. Worth doing; not worth doing before importer and assignment rules exist to handle the volume |
| **Merge duplicates** | Stage 0 + 5.6 prevent most duplicates. Merge is the remedy for the ones that got through — build it once real data shows how they arise |
| **`Account.parent_account_id`** | Genuinely useful for enterprise customers; no current demand signal in the code |
| **Email integration** | `ActivityType.EMAIL` exists with nothing producing rows. Large surface, needs its own design |
| **Notifications delivery** | The module exists with no router. Needed by Stage 4; scope it there |
| **Territories, layouts, custom fields** | `[NO]` — §4.4. Revisit only against a real customer requirement, never for parity |

---

## 6.9 Summary — the plan in one view

```
Stage 0  Correct the foundations      small   ── unique indexes, C8, close-date, phone index
Stage 1  Free derivations             small   ── probability, won/lost stamping, seeding, notes
Stage 2  Bulk data                    large   ── import, export, bulk ops, undo, restore
Stage 3  Scheduler                    medium  ── job runner, org settings, execution order
Stage 4  Automation                   large   ── rollups, assignment, health, scoring, nudges
Stage 5  Workflow UX                  medium  ── related-list create, inheritance, kanban, inline
Stage 6  Differentiators              large   ── qualification, source ROI, reports, Books link
```

**If only three things get built:**

1. **The importer (Stage 2).** Without it the product cannot be adopted, only demonstrated.
2. **Stage-driven probability + terminal stamping (Stage 1).** Two small changes that make the
   pipeline numerically honest and cost almost nothing.
3. **Related-list create with context inheritance (Stage 5).** The direct answer to *"if the user
   enters this information once, how does the CRM use it everywhere else?"*

**What not to build, restated once more:** quotes, orders, invoices, products, cases, vendors,
custom modules, layout engines, territories. Half of Zoho's surface belongs to a sibling product
by explicit architectural decision, and most of the rest is configurability that exists only
because Zoho cannot know its customer. S3K can.

---

# Phase 5/6 corrections — found during implementation

Phase 5's gap analysis was built by reading models, routers and migrations. It
did **not** read every service body, and six items were classified as missing or
partial that are in fact already implemented. Recorded here rather than silently
edited above, because the difference between "we never built this" and "we built
it and forgot" changes what the plan should do next.

| Phase 5 said | Reality on `feat/platform-phase1-crm-core` | Consequence |
|---|---|---|
| **A1 stage-driven probability — "Missing, column exists, never applied"** | **Implemented** in `OpportunityService.change_stage` and `reopen`: `if stage.default_probability is not None: opportunity.win_probability = stage.default_probability` | Only the **create** path lacked it. Fixed in Stage 0, not built from scratch |
| **A2 terminal-stage stamping — "Missing"** | **Implemented** in `change_stage`, including `LossReasonRequiredError` when moving to an `is_lost` stage | Again only **create** lacked it |
| **A3 campaign rollups — "nothing computes them"** | **Implemented**: `CampaignService.recompute_metrics` derives all four fields, and `DERIVED_FIELDS` strips them from client payloads | What is missing is the **trigger**, not the computation. It runs on demand; nothing calls it on a schedule (still blocked on C3) |
| **A12 duplicate guards — "Accounts and Contacts unguarded"** | **Implemented**: `DuplicateAccountError` and `DuplicateContactEmailError`, both overridable with `allow_duplicate`, on create *and* update | Nothing to build. The real defect was elsewhere — see below |
| **A14 first-run seeding — "Missing"** | **Implemented**: `ensure_default_pipeline` with seven default stages, called from `app/bootstrap.py` | Remaining gap is narrower: organizations created through the API rather than the bootstrap path |
| **Restore endpoint — "Missing"** | `TenantScopedRepository.restore()` exists; only the **router endpoint** is absent | Stage 2 exposes it rather than implementing it |

**The lesson for the remaining stages:** read the service, not just the model and
the router. A column with no obvious writer is not evidence that nothing writes
it.

## What the Account-duplicate finding actually was

Phase 5 recommended a partial unique index on `accounts (organization_id,
lower(name))`. **That recommendation is withdrawn.** It contradicts a deliberate
product decision already in the code (`accounts/service.py`, decision C03):
duplicate account names are *warned about and overridable*, because two real
companies do share a name.

The genuine defect was narrower and worse: `LeadService._resolve_account` called
`_find_accounts_by_name(...)` and took `matches[0]`. With duplicates legal, that
made the conversion target depend on insertion order — a converted lead's whole
pipeline could attach to the wrong company, silently. The fix is to refuse to
guess (`AmbiguousConversionMatchError`) rather than to outlaw duplicates.

## Defects found during Stage 0 that Phase 5 missed entirely

1. **Phone matching was wrong, not merely slow.** `_find_contacts_by_phone`
   read the fifty oldest contacts and filtered them in Python. Past fifty
   contacts a real match was invisible, so conversion created a duplicate
   contact and reported success. Phase 5 recorded this as a performance note.
2. **Lead conversion accepted a cross-tenant `stage_id`.** The router passed
   `payload.stage_id` straight through and `_first_stage_id` used it without an
   organization check; the foreign key is on `pipeline_stages.id` alone. A
   caller who knew another tenant's stage id could attach their opportunity to
   that tenant's pipeline. This is a tenant-isolation defect and nothing in the
   analysis predicted it.
3. **Opportunity creation wrote no stage history.** `opportunity_stage_history`
   was appended only on *movement*, so a deal's opening stage — the one every
   time-in-first-stage calculation needs — had no row.
4. **Conversion produced deals with no close date**, which is the exact hole
   §5.4 identified for hand-created deals, on a path Phase 5 did not check.

---

# Implementation status — what was actually built

Recorded against the plan in Phase 6. Where the analysis was wrong, the
correction stands above rather than being edited away, and this section says
what shipped.

## Stage 0 — Foundations ✅

| Item | Outcome |
|---|---|
| Account linking ambiguity | `AmbiguousConversionMatchError`. The Phase 5 recommendation (a unique index on account names) was **withdrawn**: it contradicts decision C03, which deliberately allows duplicate names. The defect was conversion taking `matches[0]`, not the duplicates |
| Lead lifecycle (C8) | `NEW → CONTACTED → QUALIFIED → convert()`. `PROPOSAL_SENT`/`NEGOTIATION` kept as legal *sources* so existing rows are not stranded |
| Phone matching | `contacts.phone_digits` generated column, indexed. Was **wrong, not just slow**: it read the fifty oldest contacts, so a match on the fifty-first was invisible and conversion silently duplicated |
| Close date / terminal state | `expected_close_date` NOT NULL; `create_opportunity()` applies stage probability, stamps `won_at`/`lost_at`, writes the opening stage-history row |
| *(unplanned)* | Conversion accepted a **cross-tenant `stage_id`** — a tenant-isolation defect the analysis did not predict |

## Stage 1 — Derivations ✅

Lead notes move to what the lead became (moved, not copied — three copies drift)
with `origin_entity_*` preserving provenance. Weighted pipeline
(`deal_value × win_probability`) as total, per stage and KPI, visibility-filtered.
Declarative stage follow-up tasks with duplicate suppression. Idempotent
lead-source seeding.

## Stage 2 — Bulk data ✅

CSV import with auto-mapping, preview sharing the commit code path, per-row
errors numbered as the spreadsheet numbers them, add/update/both, relation
resolution by name, and `skip_empty_values` on by default. Bounded 30-day undo
that removes only what the import *created*. Export implementing the `EXPORT`
permission the catalogue had promised since the beginning. Bulk update,
archive, restore, owner assignment and stage moves.

**A test caught a real bug**: the importer created unowned records, and
record-level visibility treats unowned rows as visible organization-wide — an
import would have published every row to every user in the tenant.

## Stage 3 — Scheduler ✅

PostgreSQL-backed queue: `FOR UPDATE SKIP LOCKED` claiming, a partial unique
index for idempotency, stale-claim recovery, retries with backoff recorded on a
*fresh* transaction, per-job tenant context, and job history.

Writing the RLS test exposed a design point worth keeping: **claiming must scan
across tenants** while **handlers must be scoped to one**, so the runner takes a
separate `handler_session_factory` and the docstring states what a deployment
needs.

## Stage 4 — Automation ✅ (backend)

Assignment rules on **every** creation path — the hook sits in
`TenantScopedService.create`, the choke point every CRM service creates through,
plus the importer. Zoho skips manual creation; S3K does not. Lead, contact and
account-health scoring, off by default and explaining themselves. Campaign
rollups now run on a schedule. Stale-lead, stale-opportunity and closing-soon
nudges with duplicate suppression.

**Not built:** REST endpoints for editing assignment rules and automation
settings. The tables, the resolution logic and the jobs all work and are
tested; configuring them today means a database write. This is the largest
single gap in Stage 4.

## Stage 5 — Workflow UX 🟡 partial

| Item | Status |
|---|---|
| Related-list creation with context inheritance | **Already existed** — verified, not rebuilt. Account→Contact, Account→Opportunity, Contact→Opportunity all pre-fill and save real foreign keys |
| Stage requirements / gating | ✅ `pipeline_stages.required_fields`, empty by default |
| Kanban drag-and-drop + per-column value | ✅ Both added; dragging goes through the same handler as the select, so business rules are not bypassed |
| Inline editing | ❌ Not built |
| Mass-action UI | ❌ Backend complete; no frontend surface |
| Import/export UI | ❌ Backend complete; no frontend surface |

## Stage 6 — Differentiators 🟡 partial

| Item | Status |
|---|---|
| Source ROI reporting | ✅ Per-source funnel, answerable because `lead_sources` is an entity |
| Reports: win/loss, ageing, funnel | ✅ |
| `QualificationRecord` (BANT/MEDDICC) | ❌ Not built. The lifecycle is correct and the frontend queue still refuses to fake scores |
| Books integration boundary | ❌ Not built |

## Honest summary

Stages 0–4 are complete and tested on the backend. Stages 5 and 6 are partial:
the backend capabilities are in place and covered, but several of them have no
frontend surface yet, and two Stage 6 items (qualification records, the Books
boundary) were not started.

The pattern worth carrying forward is the one from the Phase 5 corrections:
**read the service before believing something is missing.** Related-list context
inheritance, campaign rollups, duplicate guards, stage probability and terminal
stamping were all already built. Roughly a third of what the analysis called
missing was already there.
