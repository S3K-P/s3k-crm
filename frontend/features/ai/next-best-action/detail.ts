import { DEMO_TODAY, daysFromToday, formatDate } from '@/features/ai/shared/format';
import type {
  AgendaItem,
  CallRecord,
  CallScriptSection,
  CompetitiveNote,
  DocumentRef,
  EmailDraft,
  EmailRecord,
  GrowthPlay,
  MeetingRecord,
  NbaDetail,
  NbaRecord,
  ProposalState,
  RiskItem,
  SowState,
  Stakeholder,
  TimelineEvent,
} from './types';

/* ============================================================
   NBA DETAIL COMPOSER
   Builds the full opportunity-intelligence detail for a record.

   This is deliberately a pure, deterministic function of the
   record: the same input always produces the same engagement
   history, risks and suggested communications, so the demo is
   stable across renders and reloads. When a real backend
   exists, this composer is the single boundary to replace.
   ============================================================ */

const DAY_MS = 86_400_000;

/** Shift an ISO (yyyy-mm-dd) date by a number of days. */
function shiftDate(iso: string, days: number): string {
  const base = new Date(`${iso}T00:00:00Z`).getTime() + days * DAY_MS;
  return new Date(base).toISOString().slice(0, 10);
}

/** Small deterministic seed derived from the record id. */
function seed(id: string): number {
  let total = 0;
  for (let i = 0; i < id.length; i += 1) total += id.charCodeAt(i);
  return total;
}

function pick<T>(pool: readonly T[], id: string, offset = 0): T {
  return pool[(seed(id) + offset) % pool.length];
}

const firstName = (full: string) => full.replace(/^Dr\.\s+/, '').split(' ')[0];

/* ------------------------------------------------------------
   Company-specific supporting cast
   ------------------------------------------------------------ */

interface Colleague {
  name: string;
  role: string;
}

const COMPANY_PEOPLE: Record<string, Colleague[]> = {
  'Northwind Logistics': [
    { name: 'Daniel Osei', role: 'Chief Financial Officer' },
    { name: 'Rhea Kapoor', role: 'Head of Network Operations' },
  ],
  'Vertex Manufacturing': [
    { name: 'Anneliese Braun', role: 'Chief Financial Officer' },
    { name: 'Piotr Nowak', role: 'Maintenance Systems Manager' },
  ],
  'Helios Financial Services': [
    { name: 'Nathan Grieve', role: 'Chief Information Security Officer' },
    { name: 'Priti Shah', role: 'Head of Client Operations' },
  ],
  'Brightpath Healthcare': [
    { name: 'Warren Castillo', role: 'General Counsel' },
    { name: 'Dolores Kim', role: 'Director of Procurement' },
  ],
  'Cobalt Retail Group': [
    { name: 'Nadia Haddad', role: 'Finance Director, Retail' },
    { name: 'Tom Ellery', role: 'Head of Store Systems' },
  ],
  'Lumen Energy Partners': [
    { name: 'Carlos Ibarra', role: 'Director of Asset Strategy' },
    { name: 'Freya Lindgren', role: 'Data Platform Lead' },
  ],
  'Aureus Capital': [
    { name: 'Wei Lin Toh', role: 'Head of Procurement' },
    { name: 'Gordon Blaise', role: 'Chief Operating Officer' },
  ],
  'Trellis Agritech': [
    { name: 'Nithya Raman', role: 'Head of Field Operations' },
    { name: 'Joseph Mwangi', role: 'Finance Controller' },
  ],
  'Kestrel Aerospace': [
    { name: 'Étienne Marchand', role: 'Head of Supplier Quality' },
    { name: 'Beatrice Hall', role: 'Programme Finance Lead' },
  ],
  'Meridian Hospitality': [
    { name: 'Sofia Petrova', role: 'Director of Revenue Systems' },
    { name: 'Callum Ward', role: 'Group Finance Manager' },
  ],
  'Solace Pharma': [
    { name: 'Henrik Dahl', role: 'Head of Quality Assurance' },
    { name: 'Marianne Roux', role: 'Procurement Lead, R&D' },
  ],
  'Ironclad Insurance': [
    { name: 'Curtis Vaughn', role: 'Chief Operating Officer' },
    { name: 'Alisha Prasad', role: 'Claims Systems Manager' },
  ],
  'Bluepeak Telecom': [
    { name: 'Haruki Mori', role: 'Director of Network Operations' },
    { name: 'Lena Fischer', role: 'Procurement Manager' },
  ],
  'Granite Construction Group': [
    { name: 'Sipho Dlamini', role: 'Group Finance Director' },
    { name: 'Erin Doyle', role: 'Head of Commercial' },
  ],
  'Halcyon Media': [
    { name: 'Bianca Ferraro', role: 'Finance Business Partner' },
    { name: 'Devon Clarke', role: 'Head of Data Engineering' },
  ],
  'Pinewood Education Trust': [
    { name: 'Margaret Ellis', role: 'Head of Information Governance' },
    { name: 'Alan Prentice', role: 'Finance Director' },
  ],
  'Zephyr Mobility': [
    { name: 'Katarzyna Wójcik', role: 'Head of Data Privacy' },
    { name: 'Lars Jensen', role: 'Director of Procurement' },
  ],
  'Silverline Chemicals': [
    { name: 'Denise Okonkwo', role: 'Compliance Manager' },
    { name: 'Roy Aldridge', role: 'Plant Finance Lead' },
  ],
  'Orchid BioLabs': [
    { name: 'Peter Lindholm', role: 'Chief Scientific Officer' },
    { name: 'Amara Diallo', role: 'Head of Lab Finance' },
  ],
  'Fathom Marine Services': [
    { name: 'Khalid Al-Farsi', role: 'Technical Superintendent' },
    { name: 'Grethe Nilsen', role: 'Procurement Officer' },
  ],
  'Vantage Property Group': [
    { name: 'Hugo Lefèvre', role: 'Chief Investment Officer' },
    { name: 'Marta Silva', role: 'Head of Portfolio Analytics' },
  ],
  'Copperfield Utilities': [
    { name: 'Fiona Grant', role: 'Chief Information Security Officer' },
    { name: 'Desmond Whyte', role: 'Head of Asset Management' },
  ],
  'Nimbus Cloudworks': [
    { name: 'Aiko Sato', role: 'Director of Platform Finance' },
    { name: 'Ravi Chandran', role: 'Head of Site Reliability' },
  ],
  'Sable Foods International': [
    { name: 'Ernesto Vidal', role: 'Head of Logistics' },
    { name: 'Camila Duarte', role: 'Finance Manager, Operations' },
  ],
};

const FALLBACK_PEOPLE: Colleague[] = [
  { name: 'Finance Sponsor', role: 'Chief Financial Officer' },
  { name: 'Operations Lead', role: 'Head of Operations' },
];

function colleagues(company: string): Colleague[] {
  return COMPANY_PEOPLE[company] ?? FALLBACK_PEOPLE;
}

/* ------------------------------------------------------------
   Industry-specific content pools
   ------------------------------------------------------------ */

const PAIN_POINTS: Record<string, string[]> = {
  Logistics: [
    'Shipment exceptions are discovered by customers before the operations team sees them',
    'Carrier performance is reconciled manually in spreadsheets each month',
    'No single view of in-transit inventory across regions',
  ],
  Manufacturing: [
    'Unplanned downtime is absorbed as a cost of doing business rather than measured',
    'Maintenance scheduling relies on fixed intervals, not asset condition',
    'Plant-level reporting takes six working days to consolidate',
  ],
  'Financial Services': [
    'Client onboarding takes 18 days against a 5-day service commitment',
    'Compliance evidence is assembled manually for every audit cycle',
    'Fragmented systems mean relationship managers lack a single client view',
  ],
  Healthcare: [
    'Care coordination relies on phone and fax between sites',
    'Clinical leadership has no consolidated view of patient flow',
    'Reporting effort competes directly with clinical time',
  ],
  Retail: [
    'Store-level demand forecasts are produced centrally and frequently overridden',
    'Markdown decisions are reactive rather than planned',
    'Inventory visibility differs between the warehouse and store systems',
  ],
  Energy: [
    'Asset condition data sits in three unconnected historians',
    'Outage root-cause analysis is retrospective and slow',
    'Field teams work from static maintenance schedules',
  ],
  Agritech: [
    'Yield variance between sites is understood only after harvest',
    'Field data collection is manual and inconsistently structured',
    'Agronomy recommendations are not traceable to outcomes',
  ],
  Aerospace: [
    'Supplier quality issues surface late in the build cycle',
    'Programme reporting is assembled from disconnected supplier submissions',
    'Non-conformance trends are not visible across programmes',
  ],
  Hospitality: [
    'Guest data is fragmented across booking, loyalty and property systems',
    'Revenue decisions rely on last-year comparisons rather than live demand',
    'Property teams cannot see group-level guest history',
  ],
  Pharmaceuticals: [
    'Trial data arrives in inconsistent formats from multiple CROs',
    'Data harmonisation consumes analyst time that should go to interpretation',
    'Validation evidence is rebuilt for every study',
  ],
  Insurance: [
    'Claims triage is manual, so complex claims are identified late',
    'Cycle-time reporting lags by a full month',
    'Fraud indicators are reviewed after settlement rather than before',
  ],
  Telecom: [
    'Network faults are detected by customers before monitoring flags them',
    'Assurance data is siloed by network domain',
    'Capacity planning relies on quarterly manual analysis',
  ],
  Construction: [
    'Project cost overruns are identified at month end, not in flight',
    'Subcontractor performance is tracked per project, never across the portfolio',
    'Commercial and delivery teams work from different numbers',
  ],
  Media: [
    'Audience data is split across platform and first-party systems',
    'Campaign performance reporting is assembled manually each week',
    'Editorial and commercial teams work from different audience definitions',
  ],
  Education: [
    'Student risk indicators are reviewed termly rather than continuously',
    'Reporting to trustees consumes several days of staff time each cycle',
    'Systems do not share a common student record',
  ],
  Automotive: [
    'Telematics data volume outpaces the current platform’s query capability',
    'Vehicle data is duplicated across three regional environments',
    'Engineering teams wait days for fleet-level analysis',
  ],
  Chemicals: [
    'Process safety incidents are analysed retrospectively',
    'Regulatory evidence is compiled manually per site',
    'Condition monitoring covers only a subset of critical assets',
  ],
  Biotech: [
    'Sample throughput is limited by manual scheduling between instruments',
    'Lab utilisation is not measured consistently across sites',
    'Turnaround-time commitments are missed without early warning',
  ],
  Marine: [
    'Vessel performance data is collected at port rather than continuously',
    'Fuel efficiency variance between vessels is not explained',
    'Maintenance planning depends on the superintendent’s judgement alone',
  ],
  'Real Estate': [
    'Portfolio performance reporting is rebuilt in spreadsheets each quarter',
    'Asset managers lack comparable metrics across funds',
    'Investor reporting cycles take three weeks to complete',
  ],
  Utilities: [
    'Outage prediction relies on historical averages rather than live asset data',
    'Field crew dispatch is reactive',
    'Regulatory performance reporting is manual and time-consuming',
  ],
  Technology: [
    'Observability spend is duplicated across four overlapping tools',
    'Incident context is scattered between platforms during outages',
    'Engineering teams maintain separate dashboards per service',
  ],
  'Food & Beverage': [
    'Cold-chain excursions are detected after product arrives',
    'Spoilage cost is estimated annually rather than measured',
    'Carrier temperature compliance is unverifiable',
  ],
};

const GENERIC_PAIN_POINTS = [
  'Manual reporting consumes analyst capacity every cycle',
  'Limited pipeline and performance visibility across teams',
  'Fragmented communication between operational systems',
];

const COMPETITORS: Record<string, string[]> = {
  'Financial Services': ['Meridian Analytics', 'Cardinal Systems'],
  Manufacturing: ['Axiom Industrial Software', 'Northgate Automation'],
  Healthcare: ['Caregrid Systems', 'Lyra Health Platforms'],
  Technology: ['Beacon Observability', 'Statica Cloud'],
  Telecom: ['Signalworks', 'Orbit Assurance'],
};

const DEFAULT_COMPETITORS = ['Arcadia Insight', 'Halberd Analytics'];

const CROSS_SELL_POOL: readonly GrowthPlay[] = [
  {
    offering: 'Executive Analytics Workspace',
    rationale:
      'Leadership is already consuming operational reporting second-hand through the sponsor.',
    estimatedValue: 85000,
    relevance: 'High',
    positioning: 'Position as the reporting layer the sponsor no longer has to assemble manually.',
  },
  {
    offering: 'Data Quality & Governance Module',
    rationale:
      'Source-system inconsistency was raised during discovery and will surface again at rollout.',
    estimatedValue: 62000,
    relevance: 'Medium',
    positioning: 'Frame as protecting the value of the primary investment rather than a new project.',
  },
  {
    offering: 'Integration Accelerator Pack',
    rationale:
      'Three upstream systems are in scope, and integration effort is the most common cause of delay.',
    estimatedValue: 48000,
    relevance: 'High',
    positioning: 'Present as a delivery risk reduction, priced against implementation days saved.',
  },
  {
    offering: 'Advanced Forecasting Add-on',
    rationale:
      'The stated goal is forward-looking decisions, which the base package supports only descriptively.',
    estimatedValue: 74000,
    relevance: 'Medium',
    positioning: 'Introduce after the first value review, once baseline reporting is trusted.',
  },
];

const UPSELL_POOL: readonly GrowthPlay[] = [
  {
    offering: 'Enterprise Tier Upgrade',
    rationale:
      'Projected user growth exceeds the current tier ceiling within two quarters.',
    estimatedValue: 120000,
    relevance: 'High',
    positioning: 'Anchor to the roadmap the customer described, not to licence limits.',
  },
  {
    offering: 'Managed Services (Platinum)',
    rationale:
      'The internal team is thin on platform operations experience for a deployment of this size.',
    estimatedValue: 96000,
    relevance: 'Medium',
    positioning: 'Position as time-to-value insurance for the first two quarters.',
  },
  {
    offering: 'Additional Site / Business Unit Licence',
    rationale:
      'A second site was referenced unprompted and shares the same operating model.',
    estimatedValue: 140000,
    relevance: 'High',
    positioning: 'Bundle into the current commercial cycle to avoid a second procurement process.',
  },
];

/* ------------------------------------------------------------
   Derived helpers
   ------------------------------------------------------------ */

const PROPOSAL_BY_STAGE: Record<string, ProposalState['status']> = {
  Qualification: 'Draft',
  Discovery: 'Draft',
  Proposal: 'Viewed',
  Negotiation: 'Under Review',
  'Contract Review': 'Approved',
  'Closed Won': 'Approved',
  'Closed Lost': 'Under Review',
};

const SOW_BY_STAGE: Record<string, SowState['status']> = {
  Qualification: 'Not Started',
  Discovery: 'Not Started',
  Proposal: 'Drafting',
  Negotiation: 'Shared',
  'Contract Review': 'Legal Review',
  'Closed Won': 'Approved',
  'Closed Lost': 'Shared',
};

const DAYS_IN_STAGE_BASE: Record<string, number> = {
  Qualification: 9,
  Discovery: 16,
  Proposal: 21,
  Negotiation: 27,
  'Contract Review': 12,
  'Closed Won': 4,
  'Closed Lost': 8,
};

function momentum(record: NbaRecord): NbaDetail['opportunitySummary']['momentum'] {
  const silence = Math.abs(daysFromToday(record.lastCommunication));
  if (silence >= 14) return 'Stalled';
  if (silence >= 8) return 'Slowing';
  if (record.confidence >= 82 && record.engagement === 'High') return 'Accelerating';
  return 'Steady';
}

/* ------------------------------------------------------------
   Section builders
   ------------------------------------------------------------ */

function buildMeetings(record: NbaRecord): MeetingRecord[] {
  const [exec, operator] = colleagues(record.company);
  const base = record.lastCommunication;

  const meetings: MeetingRecord[] = [
    {
      id: `${record.id}-mtg-1`,
      title: `Discovery workshop — ${record.opportunity}`,
      date: shiftDate(base, -34),
      participants: [record.leadName, operator.name, record.assignedTo],
      summary:
        `${firstName(record.leadName)}'s team walked through the current process end to end and quantified where effort is lost.`,
      outcome: 'Requirements confirmed and success measures agreed in principle',
      followUpCommitment: 'Send a written requirements summary within three working days',
    },
    {
      id: `${record.id}-mtg-2`,
      title: `Solution review — ${record.company}`,
      date: shiftDate(base, -17),
      participants: [record.leadName, operator.name, record.assignedTo, 'Solution Consulting'],
      summary:
        'Walked the proposed architecture and phasing. Most discussion time went to integration effort and internal change impact.',
      outcome: 'Capability accepted; commercial structure raised as the open question',
      followUpCommitment: 'Provide phased pricing and an implementation outline',
    },
  ];

  if (['Proposal', 'Negotiation', 'Contract Review', 'Closed Won'].includes(record.stage)) {
    meetings.push({
      id: `${record.id}-mtg-3`,
      title: `Commercial review — ${record.opportunity}`,
      date: shiftDate(base, -5),
      participants: [record.leadName, exec.name, record.assignedTo],
      summary:
        `${exec.name} (${exec.role}) joined for the first time and focused on payback period and contractual commitment length.`,
      outcome: record.previousOutcome,
      followUpCommitment: record.recommendation,
    });
  }

  return meetings;
}

function buildEmails(record: NbaRecord): EmailRecord[] {
  const base = record.lastCommunication;
  const silent = Math.abs(daysFromToday(base)) >= 10;

  return [
    {
      id: `${record.id}-eml-1`,
      subject: `${record.opportunity} — requirements summary`,
      date: shiftDate(base, -31),
      direction: 'Outbound',
      engagement: 'Replied',
      aiSummary: 'Summary accepted with two clarifications on scope boundaries.',
    },
    {
      id: `${record.id}-eml-2`,
      subject: `Re: ${record.opportunity} — commercial questions`,
      date: shiftDate(base, -19),
      direction: 'Inbound',
      engagement: 'Replied',
      aiSummary:
        `${firstName(record.leadName)} raised pricing structure and asked who else should be involved internally.`,
    },
    {
      id: `${record.id}-eml-3`,
      subject: `${record.company} — proposal and implementation outline`,
      date: shiftDate(base, -8),
      direction: 'Outbound',
      engagement: 'Link Clicked',
      aiSummary: 'Pricing section opened repeatedly; implementation appendix viewed once.',
    },
    {
      id: `${record.id}-eml-4`,
      subject: `Following up — ${record.opportunity}`,
      date: shiftDate(base, -2),
      direction: 'Outbound',
      engagement: silent ? 'No Response' : 'Opened',
      aiSummary: silent
        ? 'No reply received. Document activity continued after the email was sent.'
        : 'Opened the same day; short acknowledgement received.',
    },
  ];
}

function buildCalls(record: NbaRecord): CallRecord[] {
  const base = record.lastCommunication;
  return [
    {
      id: `${record.id}-cal-1`,
      date: shiftDate(base, -25),
      salesperson: record.assignedTo,
      durationMinutes: 34,
      outcome: 'Qualified — proceed to solution review',
      summary:
        `Confirmed the operational driver behind ${record.opportunity} and identified the internal approval path.`,
      objection: 'Concern that internal change effort would outweigh the benefit',
      followUpAction: 'Share a comparable customer rollout plan',
    },
    {
      id: `${record.id}-cal-2`,
      date: shiftDate(base, -6),
      salesperson: record.assignedTo,
      durationMinutes: 22,
      outcome: record.previousOutcome,
      summary: `Follow-up on "${record.previousAction}". ${record.reason}`,
      objection:
        record.dealRisk === 'Critical' || record.dealRisk === 'High'
          ? 'Unresolved commercial or process blocker raised on the call'
          : 'No material objection raised',
      followUpAction: record.recommendation,
    },
  ];
}

function buildStakeholders(record: NbaRecord): Stakeholder[] {
  const [exec, operator] = colleagues(record.company);
  const silent = Math.abs(daysFromToday(record.lastCommunication)) >= 10;

  return [
    {
      id: `${record.id}-stk-1`,
      name: record.leadName,
      role: record.leadTitle,
      buyingRole: 'Champion',
      influence: 'High',
      engagement: record.engagement,
      relationship: record.confidence >= 80 ? 'Strong' : 'Developing',
      keyConcern: 'Whether the team can absorb the change alongside current commitments',
    },
    {
      id: `${record.id}-stk-2`,
      name: exec.name,
      role: exec.role,
      buyingRole: 'Decision Maker',
      influence: 'High',
      engagement: silent ? 'Dormant' : 'Moderate',
      relationship: 'Weak',
      keyConcern: 'Payback period and the length of the commercial commitment',
    },
    {
      id: `${record.id}-stk-3`,
      name: operator.name,
      role: operator.role,
      buyingRole: record.stage === 'Discovery' ? 'Technical Evaluator' : 'Influencer',
      influence: 'Medium',
      engagement: 'High',
      relationship: 'Developing',
      keyConcern: 'Integration effort against existing systems and reporting continuity',
    },
  ];
}

function buildRisks(record: NbaRecord): RiskItem[] {
  const risks: RiskItem[] = [];
  const silence = Math.abs(daysFromToday(record.lastCommunication));
  const daysToClose = daysFromToday(record.expectedCloseDate);
  const [exec] = colleagues(record.company);

  if (silence >= 10) {
    risks.push({
      id: `${record.id}-risk-silence`,
      severity: silence >= 16 ? 'High' : 'Medium',
      risk: `No response for ${silence} days`,
      evidence: `Last two-way communication was ${formatDate(record.lastCommunication)}; follow-ups since have gone unanswered.`,
      impact: 'Deal slips out of the forecast period and re-engagement cost increases',
      mitigation: 'Switch channel — call the champion directly rather than sending a further email',
    });
  }

  if (record.dealRisk === 'Critical' || record.dealRisk === 'High') {
    risks.push({
      id: `${record.id}-risk-exec`,
      severity: record.dealRisk === 'Critical' ? 'Critical' : 'High',
      risk: 'Economic buyer is not actively engaged',
      evidence: `${exec.name} (${exec.role}) has no direct interaction logged in the current stage.`,
      impact: 'Commercial approval depends on a stakeholder with no relationship history',
      mitigation: 'Request a sponsored introduction through the champion with a specific 30-minute agenda',
    });
  }

  if (daysToClose <= 21 && record.stage !== 'Closed Won') {
    risks.push({
      id: `${record.id}-risk-close`,
      severity: daysToClose <= 10 ? 'High' : 'Medium',
      risk: 'Close date is at risk of slipping',
      evidence: `Expected close is ${formatDate(record.expectedCloseDate)} (${daysToClose} days out) with open items still tracked against the current stage.`,
      impact: 'Forecast accuracy for the period is affected',
      mitigation: 'Agree a written mutual close plan with named owners for each remaining step',
    });
  }

  if (record.stage === 'Proposal' || record.stage === 'Negotiation') {
    risks.push({
      id: `${record.id}-risk-pricing`,
      severity: 'Medium',
      risk: 'Commercial structure not yet agreed',
      evidence: `Pricing was the dominant topic in the last interaction: "${record.previousOutcome}".`,
      impact: 'Late-stage renegotiation compresses margin or delays signature',
      mitigation: 'Present two pre-approved commercial structures rather than reopening the discount conversation',
    });
  }

  if (risks.length === 0) {
    risks.push({
      id: `${record.id}-risk-none`,
      severity: 'Low',
      risk: 'No material risk indicators detected',
      evidence: 'Recent two-way communication, stable stage duration and no competitor activity logged.',
      impact: 'Low — monitor for change in engagement cadence',
      mitigation: 'Maintain the current cadence and confirm the next milestone in writing',
    });
  }

  return risks;
}

function buildTimeline(
  record: NbaRecord,
  meetings: MeetingRecord[],
  emails: EmailRecord[],
  calls: CallRecord[],
): TimelineEvent[] {
  const events: TimelineEvent[] = [
    ...meetings.map<TimelineEvent>(m => ({
      id: `${m.id}-tl`,
      kind: 'meeting',
      title: m.title,
      detail: m.outcome,
      date: m.date,
    })),
    ...emails.map<TimelineEvent>(e => ({
      id: `${e.id}-tl`,
      kind: 'email',
      title: `${e.direction === 'Inbound' ? 'Email received' : 'Email sent'} — ${e.subject}`,
      detail: e.aiSummary,
      date: e.date,
    })),
    ...calls.map<TimelineEvent>(c => ({
      id: `${c.id}-tl`,
      kind: 'call',
      title: `Call with ${record.leadName} (${c.durationMinutes} min)`,
      detail: c.outcome,
      date: c.date,
    })),
    {
      id: `${record.id}-tl-stage`,
      kind: 'stage',
      title: `Stage updated to ${record.stage}`,
      detail: `Moved by ${record.assignedTo} following the solution review`,
      date: shiftDate(record.lastCommunication, -(DAYS_IN_STAGE_BASE[record.stage] ?? 14)),
    },
    {
      id: `${record.id}-tl-ai`,
      kind: 'ai',
      title: 'Next Best Action generated',
      detail: record.recommendation,
      date: shiftDate(DEMO_TODAY, -1),
    },
  ];

  if (record.documents > 3) {
    events.push({
      id: `${record.id}-tl-doc`,
      kind: 'document',
      title: 'Proposal document re-opened by the customer',
      detail: 'Pricing section accounted for most of the viewing time',
      date: shiftDate(record.lastCommunication, -3),
    });
  }

  return events.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

function buildDocuments(record: NbaRecord): DocumentRef[] {
  const catalogue: Omit<DocumentRef, 'id' | 'sharedOn' | 'lastViewed'>[] = [
    { name: `${record.company} — Proposal.pdf`, type: 'PDF', sizeKb: 1840 },
    { name: 'Discovery Notes.docx', type: 'DOCX', sizeKb: 96 },
    { name: 'Pricing Model.xlsx', type: 'XLSX', sizeKb: 274 },
    { name: 'Requirements Summary.pdf', type: 'PDF', sizeKb: 512 },
    { name: 'Solution Overview.pptx', type: 'PPTX', sizeKb: 4320 },
    { name: 'Meeting Summary — Commercial Review.pdf', type: 'PDF', sizeKb: 188 },
    { name: 'Implementation Outline.pdf', type: 'PDF', sizeKb: 640 },
    { name: 'Security & Architecture Pack.pdf', type: 'PDF', sizeKb: 2260 },
    { name: 'Reference Case Study.pdf', type: 'PDF', sizeKb: 780 },
    { name: 'Draft Statement of Work.docx', type: 'DOCX', sizeKb: 152 },
    { name: 'Master Services Agreement (redlined).docx', type: 'DOCX', sizeKb: 210 },
  ];

  return catalogue.slice(0, record.documents).map((doc, index) => ({
    ...doc,
    id: `${record.id}-doc-${index + 1}`,
    sharedOn: shiftDate(record.lastCommunication, -28 + index * 4),
    lastViewed: index < 3 ? shiftDate(record.lastCommunication, -index - 1) : null,
  }));
}

function buildSuggestedEmail(record: NbaRecord): EmailDraft {
  const who = firstName(record.leadName);
  const [exec] = colleagues(record.company);

  const bodies: Record<string, string> = {
    Meeting:
      `Hi ${who},\n\nThank you for the time on ${formatDate(record.lastCommunication)} — the discussion on ${record.opportunity} was useful, particularly the points your team raised about commercial structure.\n\nThe natural next step is a short session with ${exec.name} so the commercial questions can be answered directly rather than relayed. I would suggest 30 minutes covering the value case, the phasing options and the approval path to signature.\n\nWould either Tuesday or Wednesday afternoon work? I am happy to send an agenda in advance so the time is used efficiently.\n\nBest regards,\n${record.assignedTo}`,
    Call:
      `Hi ${who},\n\nFollowing up on ${record.opportunity}. Since we last spoke on ${formatDate(record.lastCommunication)} I want to make sure nothing is blocked at your end.\n\nRather than another document, a 15-minute call would be the quickest way to confirm where things stand and what you need from us next. I have kept tomorrow afternoon and Thursday morning open.\n\nIf it is easier, reply with a time that suits and I will send an invitation.\n\nBest regards,\n${record.assignedTo}`,
    Email:
      `Hi ${who},\n\nA short note on ${record.opportunity} to keep things moving.\n\nThe outstanding item on our side is straightforward: ${record.recommendation.toLowerCase()}. Once that is confirmed we can hold the timeline we discussed and avoid any slippage against ${formatDate(record.expectedCloseDate)}.\n\nCould you let me know the expected date by the end of the week? If it would help, I can summarise the position in a single page for your internal circulation.\n\nBest regards,\n${record.assignedTo}`,
    Proposal:
      `Hi ${who},\n\nThank you for the clarity on the last call — the feedback on commercial structure was helpful and specific.\n\nI have revised the proposal for ${record.opportunity} to reflect it. The scope is unchanged; what has changed is how it is priced and phased, which should address the concern your team raised.\n\nI will send the revised document separately. Could we take 20 minutes later this week to walk through it so any remaining questions are dealt with in one pass?\n\nBest regards,\n${record.assignedTo}`,
    Content:
      `Hi ${who},\n\nAs promised, I am putting together the material you asked for on ${record.opportunity}.\n\nIt covers the specific points your team raised, so it should be usable directly in your internal review rather than needing translation. I will have it with you before your next review meeting.\n\nIf there is anyone else who should receive it, let me know and I will include them.\n\nBest regards,\n${record.assignedTo}`,
    Internal:
      `Hi ${who},\n\nThank you for your continued support on ${record.opportunity}.\n\nOne process item is holding progress rather than anything commercial, and I would like to avoid it affecting the timeline we agreed. Would you be able to point me to the right person internally, or make a brief introduction?\n\nA short note from you would carry considerably more weight than an approach from us.\n\nBest regards,\n${record.assignedTo}`,
  };

  const subjects: Record<string, string> = {
    Meeting: `${record.opportunity} — 30 minutes with ${exec.name}?`,
    Call: `${record.opportunity} — quick call this week?`,
    Email: `${record.opportunity} — confirming the next step`,
    Proposal: `Revised proposal — ${record.opportunity}`,
    Content: `${record.opportunity} — the material you asked for`,
    Internal: `${record.opportunity} — a quick introduction`,
  };

  return {
    subject: subjects[record.channel] ?? subjects.Email,
    body: bodies[record.channel] ?? bodies.Email,
  };
}

function buildWhatsapp(record: NbaRecord): string {
  const who = firstName(record.leadName);
  return (
    `Hi ${who}, ${record.assignedTo} here from S3K. ` +
    `Quick note on ${record.opportunity} — I have kept two slots open this week to close out the last open point. ` +
    `Would Wednesday 3pm or Thursday 11am suit you better? Happy to keep it to 20 minutes.`
  );
}

function buildCallScript(record: NbaRecord): CallScriptSection[] {
  const who = firstName(record.leadName);
  const [exec] = colleagues(record.company);

  return [
    {
      label: 'Opening',
      lines: [
        `"Hi ${who}, thanks for taking a few minutes — I know things are busy at ${record.company}."`,
        '"I have one specific thing I want to close out, and then I will let you go."',
      ],
    },
    {
      label: 'Context',
      lines: [
        `"When we last spoke on ${formatDate(record.lastCommunication)}, the outcome was: ${record.previousOutcome.toLowerCase()}."`,
        `"Since then I have been working on ${record.opportunity}, and I want to make sure we are still aligned on timing."`,
      ],
    },
    {
      label: 'Discovery questions',
      lines: [
        '"Where does this sit against your other priorities this quarter?"',
        `"Who else needs to be comfortable before ${record.company} can commit?"`,
        '"Is there anything that has changed internally since we last spoke?"',
        `"What would need to be true for this to be signed by ${formatDate(record.expectedCloseDate)}?"`,
      ],
    },
    {
      label: 'Value positioning',
      lines: [
        `"The outcome your team described was removing the manual effort in ${record.industry.toLowerCase()} reporting — that is what the first phase is scoped to deliver."`,
        '"Comparable customers reached that point within one quarter of go-live, not a full year."',
      ],
    },
    {
      label: 'Objection handling',
      lines: [
        '"If cost is the concern — the structure is flexible; the scope does not have to change to change the commercial shape."',
        '"If timing is the concern — we can align the start date to your cycle, but the approval path takes as long as it takes, so starting it now protects your date."',
        '"If it is an internal comparison — I would rather help you make a fair comparison than avoid the question."',
      ],
    },
    {
      label: 'Closing / next step',
      lines: [
        `"The clearest next step is: ${record.recommendation.toLowerCase()}."`,
        `"Could you introduce me to ${exec.name}, or would you prefer to take the commercial questions internally first?"`,
        '"Either way, can we agree a date now so it does not drift?"',
      ],
    },
  ];
}

function buildAgenda(record: NbaRecord): AgendaItem[] {
  const [exec] = colleagues(record.company);
  return [
    {
      topic: 'Business priorities and what has changed',
      minutes: 5,
      objective: 'Confirm the operational driver is still ranked as it was at discovery',
      participants: `${record.leadName}, ${record.assignedTo}`,
    },
    {
      topic: 'Current challenges and quantified impact',
      minutes: 10,
      objective: 'Agree the baseline numbers the business case will be measured against',
      participants: `${record.leadName}, operations stakeholders`,
    },
    {
      topic: `Solution alignment — ${record.opportunity}`,
      minutes: 10,
      objective: 'Validate scope and phasing against the confirmed requirements',
      participants: 'Full working group',
    },
    {
      topic: 'Commercial considerations',
      minutes: 10,
      objective: 'Resolve pricing structure and contract term in a single conversation',
      participants: `${exec.name}, ${record.assignedTo}`,
    },
    {
      topic: 'Agreed next steps and owners',
      minutes: 5,
      objective: 'Leave with named owners and dates for every remaining step to signature',
      participants: 'All attendees',
    },
  ];
}

function buildCompetitiveNotes(record: NbaRecord): CompetitiveNote[] {
  const pool = COMPETITORS[record.industry] ?? DEFAULT_COMPETITORS;
  const competitor = pick(pool, record.id);

  return [
    {
      competitor,
      customerConcern: `${competitor} has quoted a shorter implementation window at a lower entry price.`,
      competitorStrength: 'Aggressive first-year pricing and a familiar name in the sector',
      response:
        'Compare total cost across three years including integration effort, and offer a reference call with a customer who ran the same evaluation.',
    },
    {
      competitor: 'Internal build',
      customerConcern: 'The data team believes a first version could be built in-house in one quarter.',
      competitorStrength: 'Full control and no licence cost',
      response:
        'Acknowledge feasibility of version one, then focus the conversation on ongoing maintenance ownership and the opportunity cost to the data team.',
    },
  ];
}

/* ------------------------------------------------------------
   Public composer
   ------------------------------------------------------------ */

export function buildNbaDetail(record: NbaRecord): NbaDetail {
  const meetings = buildMeetings(record);
  const emails = buildEmails(record);
  const calls = buildCalls(record);
  const silence = Math.abs(daysFromToday(record.lastCommunication));
  const daysInStage = (DAYS_IN_STAGE_BASE[record.stage] ?? 14) + (seed(record.id) % 11);
  const [exec] = colleagues(record.company);

  return {
    recordId: record.id,

    opportunitySummary: {
      name: record.opportunity,
      stage: record.stage,
      dealSize: record.expectedRevenue,
      winProbability: record.winProbability,
      expectedCloseDate: record.expectedCloseDate,
      daysInStage,
      lastActivity: record.previousAction,
      nextMilestone: record.recommendation,
      momentum: momentum(record),
    },

    leadSummary: {
      name: record.leadName,
      company: record.company,
      title: record.leadTitle,
      email: record.email,
      phone: record.phone,
      leadSource: record.leadSource,
      owner: record.assignedTo,
      engagement: record.engagement,
    },

    meetings,
    emails,
    calls,
    timeline: buildTimeline(record, meetings, emails, calls),

    painPoints: PAIN_POINTS[record.industry] ?? GENERIC_PAIN_POINTS,
    stakeholders: buildStakeholders(record),

    aiAnalysis: {
      rationale: record.reason,
      evidence: [
        { label: 'Last two-way communication', value: `${formatDate(record.lastCommunication)} (${silence} days ago)` },
        { label: 'Days in current stage', value: `${daysInStage} days` },
        { label: 'Previous action', value: `${record.previousAction} — ${record.previousOutcome}` },
        { label: 'Executive engagement', value: silence >= 10 ? `${exec.role} not engaged in this stage` : `${exec.role} engaged in the last cycle` },
        { label: 'Close-date proximity', value: `${formatDate(record.expectedCloseDate)} (${daysFromToday(record.expectedCloseDate)} days out)` },
        { label: 'Document engagement', value: `${record.documents} documents shared; proposal re-opened during the last week` },
      ],
      uncertainty:
        record.confidence >= 85
          ? 'Supporting signals are consistent. The main unknown is internal scheduling, which is outside the recorded data.'
          : record.confidence >= 70
            ? 'Engagement history supports the recommendation, but no economic buyer interaction is logged in this stage.'
            : 'Limited interaction history. Treat this recommendation as directional and re-score after the next conversation.',
    },

    highlight: {
      action: record.recommendation,
      priority: record.priority,
      timing:
        daysFromToday(record.nextFollowUp) <= 0
          ? 'Today — follow-up date has been reached'
          : `By ${formatDate(record.nextFollowUp)}`,
      owner: record.assignedTo,
      reason: record.reason,
      expectedImpact:
        record.dealRisk === 'Critical' || record.dealRisk === 'High'
          ? `Protects ${record.expectedRevenue >= 500000 ? 'a high-value' : 'an active'} opportunity currently exposed to slippage`
          : 'Advances the opportunity to the next stage and firms up the close date',
      confidence: record.confidence,
    },

    suggestedEmail: buildSuggestedEmail(record),
    suggestedWhatsapp: buildWhatsapp(record),
    callScript: buildCallScript(record),
    meetingAgenda: buildAgenda(record),

    proposal: {
      status: PROPOSAL_BY_STAGE[record.stage] ?? 'Draft',
      version: record.stage === 'Qualification' || record.stage === 'Discovery' ? 'v0.9 (internal)' : 'v2.1',
      sentOn:
        record.stage === 'Qualification' || record.stage === 'Discovery'
          ? null
          : shiftDate(record.lastCommunication, -8),
      lastViewed:
        record.stage === 'Qualification' || record.stage === 'Discovery'
          ? null
          : shiftDate(record.lastCommunication, -1),
      value: record.expectedRevenue,
      note:
        record.stage === 'Qualification' || record.stage === 'Discovery'
          ? 'Not yet issued — awaiting confirmed requirements sign-off.'
          : 'Pricing section carries the majority of viewing time across all opens.',
    },

    sow: {
      status: SOW_BY_STAGE[record.stage] ?? 'Not Started',
      owner: record.assignedTo,
      targetDate:
        record.stage === 'Qualification' || record.stage === 'Discovery'
          ? null
          : shiftDate(record.expectedCloseDate, -7),
      note:
        SOW_BY_STAGE[record.stage] === 'Not Started'
          ? 'Starts once the proposal is accepted in principle.'
          : 'Delivery scope mirrors the phased approach in the current proposal.',
    },

    crossSell: [pick(CROSS_SELL_POOL, record.id), pick(CROSS_SELL_POOL, record.id, 1)],
    upsell:
      record.expectedRevenue >= 300000
        ? [pick(UPSELL_POOL, record.id), pick(UPSELL_POOL, record.id, 1)]
        : [],

    risks: buildRisks(record),
    competitiveNotes: buildCompetitiveNotes(record),
    documents: buildDocuments(record),
  };
}
