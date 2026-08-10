import { NBA_RECORDS } from '@/features/ai/next-best-action/mock-data';
import type { OpportunityStage } from '@/features/ai/next-best-action/types';
import type {
  AiInsightReport,
  SalesIntelligenceSnapshot,
  SeriesPoint,
} from './types';

/* ============================================================
   AI INSIGHTS — MOCK DATASET

   Three curated account intelligence reports plus the
   portfolio-level Sales Intelligence Snapshot. Reports are
   written to be internally coherent with the Next Best Action
   dataset: the same accounts, owners, values and dates.

   All companies and people are fictional.
   ============================================================ */

export const STAGE_ORDER: OpportunityStage[] = [
  'Qualification',
  'Discovery',
  'Proposal',
  'Negotiation',
  'Contract Review',
  'Closed Won',
];

export const SUGGESTED_PROMPTS: string[] = [
  'Show me pipeline health',
  'Which deals are at risk?',
  'Summarize Northwind Logistics',
  'Which opportunities need attention?',
  'Generate weekly sales summary',
  'Show high-value deals closing this month',
  'Which leads have gone cold?',
];

export const ANALYSIS_CAPABILITIES: { title: string; description: string }[] = [
  {
    title: 'Account intelligence',
    description: 'Consolidated view of an account: relationship, stakeholders and open commitments.',
  },
  {
    title: 'Deal-risk analysis',
    description: 'Surfaces the evidence behind slippage risk and the mitigation that addresses it.',
  },
  {
    title: 'Buying signals',
    description: 'Document engagement, stakeholder movement and commercial questions worth acting on.',
  },
  {
    title: 'Pipeline analysis',
    description: 'Stage position, velocity and where an opportunity sits against comparable deals.',
  },
  {
    title: 'Communication intelligence',
    description: 'Response trends, sentiment and the questions still waiting on an answer.',
  },
  {
    title: 'Follow-up recommendations',
    description: 'Prioritised next actions with owner, timing and the outcome each one targets.',
  },
];

/* ------------------------------------------------------------
   Report 1 — Northwind Logistics (healthy, proposal stage)
   ------------------------------------------------------------ */

const NORTHWIND: AiInsightReport = {
  id: 'insight-northwind',
  subject: 'Northwind Logistics',
  headline:
    'Active proposal with strong operational sponsorship. Finance has entered the evaluation and now needs a direct commercial conversation.',
  primaryRecommendation: 'Schedule a commercial review with Daniel Osei (CFO) within 48 hours',
  topRisk: 'No commercial owner is engaged while the proposal is being actively re-read',

  customerSummary: {
    company: 'Northwind Logistics',
    primaryContact: 'Meera Krishnan',
    contactTitle: 'VP Supply Chain',
    industry: 'Logistics',
    relationshipStage: 'Active opportunity — second engagement cycle',
    accountOwner: 'Priya Patel',
    lastInteraction: '2026-08-05',
    opportunity: 'Fleet Visibility Platform — Phase 1',
    opportunityValue: 480000,
    expectedCloseDate: '2026-09-18',
    narrative:
      'Northwind approached S3K after a webinar on carrier performance reconciliation. Operations has run a thorough evaluation over eleven weeks, with Meera Krishnan sponsoring throughout. The proposal covers phase one only — fleet visibility across two regions — with a stated intent to extend if the first phase holds its service commitments. The evaluation has recently widened from operations into finance, which is normal for this account size and generally a positive signal.',
  },

  relationshipScore: {
    score: 78,
    tier: 'Healthy',
    rationale:
      'Consistent two-way communication with a committed operational sponsor. The score is held below "Strong" because no relationship exists with the finance stakeholder who will approve the spend.',
    factors: [
      { label: 'Communication recency', value: 92, note: 'Last two-way exchange 2 days ago' },
      { label: 'Response rate', value: 88, note: '11 of 12 emails answered within a working day' },
      { label: 'Meeting engagement', value: 84, note: 'Six meetings, all attended by the sponsor' },
      { label: 'Decision-maker access', value: 45, note: 'CFO observed one meeting; no direct contact' },
      { label: 'Proposal activity', value: 81, note: 'Proposal re-opened four times in six days' },
    ],
  },

  buyingSignals: [
    {
      id: 'nw-sig-1',
      signal: 'CFO joined the latest review',
      date: '2026-08-05',
      strength: 'Strong',
      explanation:
        'Daniel Osei attended unannounced and asked for a three-year cost model — a question finance only asks when a purchase is being seriously considered.',
    },
    {
      id: 'nw-sig-2',
      signal: 'Proposal re-opened four times in six days',
      date: '2026-08-04',
      strength: 'Strong',
      explanation:
        'Repeat opens are concentrated on the pricing and commercial-terms sections rather than capability.',
    },
    {
      id: 'nw-sig-3',
      signal: 'Implementation timeline requested',
      date: '2026-07-30',
      strength: 'Moderate',
      explanation:
        'Operations asked how quickly phase one could start, which indicates internal planning has begun.',
    },
    {
      id: 'nw-sig-4',
      signal: 'Multiple stakeholders engaged',
      date: '2026-07-28',
      strength: 'Moderate',
      explanation:
        'Network operations joined the working group, extending the evaluation beyond the original sponsor.',
    },
    {
      id: 'nw-sig-5',
      signal: 'Contract questions raised',
      date: '2026-07-24',
      strength: 'Emerging',
      explanation:
        'A question on notice periods was raised informally — early, but usually a late-cycle topic.',
    },
  ],

  salesHealth: {
    dealHealth: 'Healthy',
    winProbability: 68,
    momentum: 'Steady',
    daysInStage: 24,
    nextMilestone: 'Commercial review with finance',
    targetCloseDate: '2026-09-18',
    note: 'Stage duration is slightly above the 19-day average for comparable proposals, driven by the widened buying committee rather than lost interest.',
  },

  pipelinePosition: {
    currentStage: 'Proposal',
    stageOrder: STAGE_ORDER,
    pipelineHealth: 'Above average for the segment',
    averageStageDays: 19,
    note: 'Two stages remain. Comparable deals that engaged finance at this point closed within 34 days on average.',
  },

  risks: [
    {
      id: 'nw-risk-1',
      severity: 'High',
      risk: 'Decision maker not engaged',
      evidence:
        'Daniel Osei (CFO) has observed one meeting and has no direct interaction logged with the account team.',
      impact: 'Commercial approval rests with a stakeholder who has no relationship with S3K',
      mitigation: 'Request a 30-minute commercial review through Meera Krishnan with a pre-sent agenda',
    },
    {
      id: 'nw-risk-2',
      severity: 'Medium',
      risk: 'Pricing structure unresolved',
      evidence:
        'Pricing accounts for most viewing time across four proposal opens, with no written feedback received.',
      impact: 'Late-cycle discount pressure or an unplanned scope reduction',
      mitigation: 'Present two pre-approved commercial structures instead of waiting for an objection',
    },
    {
      id: 'nw-risk-3',
      severity: 'Low',
      risk: 'Phase two scope undefined',
      evidence: 'Extension intent is verbal only and appears in no document.',
      impact: 'Expansion revenue is unforecastable and may require a separate procurement cycle',
      mitigation: 'Reference phase two as an option in the current order form',
    },
  ],

  activities: [
    { id: 'nw-act-1', type: 'meeting', title: 'Commercial review — Fleet Visibility Platform', detail: 'CFO joined; three-year cost model requested', date: '2026-08-05' },
    { id: 'nw-act-2', type: 'document', title: 'Proposal re-opened by the customer', detail: 'Pricing section viewed twice in one session', date: '2026-08-04' },
    { id: 'nw-act-3', type: 'email', title: 'Email sent — revised proposal with tiered pricing', detail: 'Opened four times; no reply received', date: '2026-08-01' },
    { id: 'nw-act-4', type: 'call', title: 'Follow-up call with Meera Krishnan (22 min)', detail: 'Confirmed internal approval path and timing', date: '2026-07-30' },
    { id: 'nw-act-5', type: 'stage', title: 'Stage updated to Proposal', detail: 'Moved by Priya Patel after solution review', date: '2026-07-12' },
    { id: 'nw-act-6', type: 'meeting', title: 'Solution review — Northwind Logistics', detail: 'Capability accepted; commercial structure raised', date: '2026-07-08' },
  ],

  communication: {
    lastCommunication: '2026-08-05',
    responseTrend: 'Stable — response times have not lengthened across the cycle',
    averageResponseHours: 9,
    engagementLevel: 'High',
    sentiment: 'Positive',
    openQuestions: [
      'What does the three-year total cost look like including integration?',
      'Can phase one start before the end of the quarter?',
      'What notice period applies if phase two is not taken up?',
    ],
    currentGapDays: 2,
  },

  decisionMakers: [
    { id: 'nw-dm-1', name: 'Meera Krishnan', role: 'VP Supply Chain', buyingRole: 'Champion', influence: 'High', engagement: 'High', relationship: 'Strong', keyConcern: 'Whether her team can absorb the rollout alongside peak season' },
    { id: 'nw-dm-2', name: 'Daniel Osei', role: 'Chief Financial Officer', buyingRole: 'Decision Maker', influence: 'High', engagement: 'Low', relationship: 'Weak', keyConcern: 'Three-year cost exposure and payback period' },
    { id: 'nw-dm-3', name: 'Rhea Kapoor', role: 'Head of Network Operations', buyingRole: 'Technical Evaluator', influence: 'Medium', engagement: 'High', relationship: 'Developing', keyConcern: 'Integration effort against the existing carrier portal' },
    { id: 'nw-dm-4', name: 'Procurement (unnamed)', role: 'Procurement', buyingRole: 'Procurement', influence: 'Medium', engagement: 'Dormant', relationship: 'Weak', keyConcern: 'Not yet engaged — expected to enter at contract stage' },
  ],

  opportunities: [
    { id: 'nw-opp-1', name: 'Fleet Visibility Platform — Phase 1', stage: 'Proposal', value: 480000, probability: 68, expectedCloseDate: '2026-09-18', nextMilestone: 'Commercial review with finance', health: 'Healthy' },
    { id: 'nw-opp-2', name: 'Fleet Visibility — Phase 2 (EMEA)', stage: 'Qualification', value: 260000, probability: 20, expectedCloseDate: '2027-01-29', nextMilestone: 'Confirm scope in the phase one order form', health: 'Watch' },
  ],

  followUps: [
    { id: 'nw-fu-1', priority: 'Critical', action: 'Schedule a commercial review with Daniel Osei within 48 hours', owner: 'Priya Patel', timing: 'By 9 Aug', reason: 'The CFO has entered the evaluation and asked a commercial question that has not been answered directly.', expectedOutcome: 'Named commercial owner and an agreed approval path' },
    { id: 'nw-fu-2', priority: 'High', action: 'Send the three-year total cost model with integration effort included', owner: 'Priya Patel', timing: 'Before the review', reason: 'Answering the CFO’s exact question ahead of the meeting removes one round trip.', expectedOutcome: 'Commercial conversation starts from agreed numbers' },
    { id: 'nw-fu-3', priority: 'Medium', action: 'Confirm phase one start date with Rhea Kapoor', owner: 'Priya Patel', timing: 'This week', reason: 'Operations has begun internal planning and needs a date to schedule against.', expectedOutcome: 'Delivery timeline anchored, creating urgency to sign' },
    { id: 'nw-fu-4', priority: 'Medium', action: 'Reference phase two as a priced option in the order form', owner: 'Priya Patel', timing: 'Before contract issue', reason: 'Extension intent is currently verbal and unforecastable.', expectedOutcome: 'Expansion revenue becomes visible in the pipeline' },
  ],

  suggestedEmail: {
    subject: 'Fleet Visibility Platform — 30 minutes with Daniel?',
    body:
      'Hi Meera,\n\nThank you for the session on 5 August — and for bringing Daniel in. His question on the three-year cost position is a fair one, and it is better answered directly than through you.\n\nCould we find 30 minutes with him this week? I would cover three things: the total cost position including integration, the two commercial structures available, and what the approval path to a September start looks like.\n\nI will send the cost model in advance so the time is spent on decisions rather than on numbers.\n\nWould Tuesday or Wednesday afternoon suit?\n\nBest regards,\nPriya Patel',
  },

  callScript: [
    { label: 'Opening', lines: ['"Hi Meera, thanks for making time — I will keep this to fifteen minutes."', '"I have one thing I would like to agree with you, and then I will get out of your way."'] },
    { label: 'Context', lines: ['"Daniel joined the review on the 5th and asked about the three-year cost position."', '"That tells me finance is now part of this, which is good — but it also means we are answering his question second-hand."'] },
    { label: 'Discovery questions', lines: ['"How does Daniel usually want commercial cases presented?"', '"Is there an approval threshold or committee this has to pass through?"', '"What would make you comfortable putting the two of us in a room together?"'] },
    { label: 'Value positioning', lines: ['"Phase one is scoped to remove the manual carrier reconciliation your team described — that is roughly four working days a month."', '"Comparable logistics customers reached that point inside one quarter of go-live."'] },
    { label: 'Objection handling', lines: ['"If the concern is the three-year commitment — the structure is flexible without changing scope."', '"If the concern is peak season — we can align the start date so nothing lands in your busiest weeks."'] },
    { label: 'Closing / next step', lines: ['"Can we put 30 minutes in with Daniel this week?"', '"If you would rather take the commercial questions internally first, I will send you everything you need — but I would prefer to answer him directly."'] },
  ],

  meetingAgenda: [
    { topic: 'Business priorities and what has changed', minutes: 5, objective: 'Confirm the operational driver still ranks as it did at discovery', participants: 'Meera Krishnan, Priya Patel' },
    { topic: 'Current challenges and quantified impact', minutes: 10, objective: 'Agree the baseline the business case is measured against', participants: 'Meera Krishnan, Rhea Kapoor' },
    { topic: 'Solution alignment — phase one scope', minutes: 10, objective: 'Validate scope and phasing against confirmed requirements', participants: 'Full working group' },
    { topic: 'Commercial considerations', minutes: 10, objective: 'Resolve the three-year cost position and contract term in one conversation', participants: 'Daniel Osei, Priya Patel' },
    { topic: 'Agreed next steps and owners', minutes: 5, objective: 'Leave with named owners and dates through to signature', participants: 'All attendees' },
  ],

  confidence: {
    score: 88,
    tier: 'High Confidence',
    rationale: [
      'Recent two-way communication available (2 days ago)',
      'Opportunity record updated within the last week',
      'Six stakeholder interactions logged across two functions',
      'Sustained proposal engagement detected',
    ],
    uncertainty:
      'The CFO’s internal position is inferred from one meeting and one question. Treat the commercial read as directional until a direct conversation happens.',
  },

  importantNotes: [
    'AI-generated recommendations should be reviewed against the latest customer context before action.',
    'Phase two figures are indicative — the extension has been discussed verbally but appears in no document.',
  ],

  keyTakeaways: [
    'The deal is healthy, but decision-maker engagement is incomplete.',
    'Finance entering the evaluation is a positive signal, not a warning sign.',
    'Pricing discussion should happen before the customer forms a position internally.',
    'The best next action is an executive commercial meeting within 48 hours.',
  ],
};

/* ------------------------------------------------------------
   Report 2 — Vertex Manufacturing (at risk, negotiation)
   ------------------------------------------------------------ */

const VERTEX: AiInsightReport = {
  id: 'insight-vertex',
  subject: 'Vertex Manufacturing',
  headline:
    'Late-stage deal losing momentum. Executive contact has lapsed for three weeks while a competitor has been named and the close date sits after the customer’s budget freeze.',
  primaryRecommendation: 'Re-engage Anneliese Braun (CFO) before the 14 August budget lock',
  topRisk: 'Close date falls two days after the customer’s stated budget freeze',

  customerSummary: {
    company: 'Vertex Manufacturing',
    primaryContact: 'Thomas Reinhardt',
    contactTitle: 'Director of Plant Operations',
    industry: 'Manufacturing',
    relationshipStage: 'Late-stage negotiation',
    accountOwner: 'Mike Johnson',
    lastInteraction: '2026-07-24',
    opportunity: 'Predictive Maintenance Rollout',
    opportunityValue: 725000,
    expectedCloseDate: '2026-08-16',
    narrative:
      'Vertex was an outbound target account opened nine months ago. Thomas Reinhardt has championed the programme consistently and the technical evaluation is complete across two plants. Commercial terms were close to agreement in early July, after which executive contact stopped. A competitor was named on the final call, and the customer has since referenced a budget freeze from 14 August. The deal is not lost, but it is no longer progressing on its own.',
  },

  relationshipScore: {
    score: 54,
    tier: 'Moderate',
    rationale:
      'A strong single relationship is carrying the deal. Executive contact has lapsed at exactly the point where executive sponsorship matters most.',
    factors: [
      { label: 'Communication recency', value: 32, note: 'Last two-way exchange 14 days ago' },
      { label: 'Response rate', value: 61, note: 'Champion responsive; economic buyer silent for 21 days' },
      { label: 'Meeting engagement', value: 74, note: 'Eight meetings, but none with finance since 3 July' },
      { label: 'Decision-maker access', value: 28, note: 'No direct CFO contact in the current stage' },
      { label: 'Proposal activity', value: 66, note: 'ROI model opened twice; no document activity in 9 days' },
    ],
  },

  buyingSignals: [
    { id: 'vx-sig-1', signal: 'Technical validation completed across both plants', date: '2026-07-18', strength: 'Strong', explanation: 'Engineering sign-off removes the largest non-commercial obstacle.' },
    { id: 'vx-sig-2', signal: 'ROI model reviewed by the champion', date: '2026-07-22', strength: 'Moderate', explanation: 'Thomas responded positively and shared it internally.' },
    { id: 'vx-sig-3', signal: 'Implementation timeline requested', date: '2026-07-11', strength: 'Moderate', explanation: 'Plant operations asked how a phased rollout would sequence across sites.' },
    { id: 'vx-sig-4', signal: 'Contract questions raised', date: '2026-07-03', strength: 'Emerging', explanation: 'Legal raised liability caps informally, then went quiet.' },
  ],

  salesHealth: {
    dealHealth: 'At Risk',
    winProbability: 72,
    momentum: 'Stalled',
    daysInStage: 31,
    nextMilestone: 'Commercial re-engagement with the economic buyer',
    targetCloseDate: '2026-08-16',
    note: 'Momentum has moved from accelerating to stalled over two weeks. Win probability still reflects technical position rather than current commercial reality.',
  },

  pipelinePosition: {
    currentStage: 'Negotiation',
    stageOrder: STAGE_ORDER,
    pipelineHealth: 'Below average — stage duration exceeds the segment norm by 63%',
    averageStageDays: 19,
    note: 'Deals that pass 30 days in negotiation without executive contact close at roughly half the rate of those that do not.',
  },

  risks: [
    { id: 'vx-risk-1', severity: 'Critical', risk: 'Close date falls after the customer’s budget freeze', evidence: 'Customer stated a 14 August budget lock; expected close is 16 August.', impact: 'Deal slips a full quarter regardless of commercial agreement', mitigation: 'Agree a written close plan this week, or reset the close date to reflect the next budget cycle' },
    { id: 'vx-risk-2', severity: 'High', risk: 'Economic buyer disengaged for 21 days', evidence: 'No interaction with Anneliese Braun (CFO) logged since 17 July.', impact: 'No route to commercial approval inside the current window', mitigation: 'Request a sponsored introduction from Thomas with a specific 30-minute agenda' },
    { id: 'vx-risk-3', severity: 'High', risk: 'Competitor named without response', evidence: 'Axiom Industrial Software was referenced on the 24 July call; no counter-position has been provided.', impact: 'Customer forms a comparison view from the competitor’s framing alone', mitigation: 'Send a three-year total cost comparison including integration effort' },
    { id: 'vx-risk-4', severity: 'Medium', risk: 'Single-threaded on the champion', evidence: 'Seven of eight logged interactions involve Thomas Reinhardt.', impact: 'Deal is exposed to one person’s availability and internal standing', mitigation: 'Bring maintenance systems and finance into the next working session' },
  ],

  activities: [
    { id: 'vx-act-1', type: 'call', title: 'Negotiation call with Thomas Reinhardt (28 min)', detail: 'Competitor named; budget freeze mentioned', date: '2026-07-24' },
    { id: 'vx-act-2', type: 'email', title: 'Email sent — ROI model and reference deck', detail: 'Opened twice by the champion; no finance engagement', date: '2026-07-22' },
    { id: 'vx-act-3', type: 'meeting', title: 'Technical validation — Plant 2', detail: 'Engineering sign-off obtained', date: '2026-07-18' },
    { id: 'vx-act-4', type: 'meeting', title: 'Commercial terms discussion', detail: 'Last meeting attended by finance', date: '2026-07-03' },
    { id: 'vx-act-5', type: 'stage', title: 'Stage updated to Negotiation', detail: 'Moved by Mike Johnson following technical sign-off', date: '2026-07-01' },
    { id: 'vx-act-6', type: 'proposal', title: 'Proposal v2.1 issued', detail: 'Phased rollout across two plants', date: '2026-06-26' },
  ],

  communication: {
    lastCommunication: '2026-07-24',
    responseTrend: 'Deteriorating — average response time has tripled since early July',
    averageResponseHours: 62,
    engagementLevel: 'Moderate',
    sentiment: 'Mixed',
    openQuestions: [
      'How does the total cost compare with the alternative under evaluation?',
      'Can anything be signed before the 14 August budget lock?',
      'What liability cap is acceptable to Vertex legal?',
    ],
    currentGapDays: 14,
  },

  decisionMakers: [
    { id: 'vx-dm-1', name: 'Thomas Reinhardt', role: 'Director of Plant Operations', buyingRole: 'Champion', influence: 'High', engagement: 'Moderate', relationship: 'Strong', keyConcern: 'Whether the rollout can be delivered without disrupting production' },
    { id: 'vx-dm-2', name: 'Anneliese Braun', role: 'Chief Financial Officer', buyingRole: 'Decision Maker', influence: 'High', engagement: 'Dormant', relationship: 'Weak', keyConcern: 'Capital commitment ahead of the budget freeze' },
    { id: 'vx-dm-3', name: 'Piotr Nowak', role: 'Maintenance Systems Manager', buyingRole: 'Technical Evaluator', influence: 'Medium', engagement: 'High', relationship: 'Developing', keyConcern: 'Integration with the existing maintenance management system' },
    { id: 'vx-dm-4', name: 'Vertex Legal', role: 'General Counsel', buyingRole: 'Blocker', influence: 'Medium', engagement: 'Dormant', relationship: 'Weak', keyConcern: 'Liability caps raised informally and never resolved' },
  ],

  opportunities: [
    { id: 'vx-opp-1', name: 'Predictive Maintenance Rollout', stage: 'Negotiation', value: 725000, probability: 72, expectedCloseDate: '2026-08-16', nextMilestone: 'CFO commercial re-engagement', health: 'At Risk' },
    { id: 'vx-opp-2', name: 'Plant 3 Extension', stage: 'Qualification', value: 310000, probability: 15, expectedCloseDate: '2027-02-26', nextMilestone: 'Dependent on phase one outcome', health: 'Watch' },
  ],

  followUps: [
    { id: 'vx-fu-1', priority: 'Critical', action: 'Request a CFO introduction from Thomas today', owner: 'Mike Johnson', timing: 'Today', reason: 'Twenty-one days of executive silence with nine days until the budget lock leaves no room for a slower route.', expectedOutcome: 'Direct commercial conversation before the freeze' },
    { id: 'vx-fu-2', priority: 'Critical', action: 'Agree a written close plan or formally reset the close date', owner: 'Mike Johnson', timing: 'By 11 Aug', reason: 'The current close date is two days after the customer’s stated freeze, so the forecast is unreliable as it stands.', expectedOutcome: 'Accurate forecast and a realistic path to signature' },
    { id: 'vx-fu-3', priority: 'High', action: 'Send a three-year cost comparison addressing the competitor position', owner: 'Mike Johnson', timing: 'Before the CFO conversation', reason: 'A competitor was named 14 days ago and no counter-position has been supplied.', expectedOutcome: 'Customer evaluates on total cost rather than entry price' },
    { id: 'vx-fu-4', priority: 'High', action: 'Resolve the liability cap question with Vertex legal', owner: 'Mike Johnson', timing: 'This week', reason: 'An unresolved legal question raised in early July will resurface at signature.', expectedOutcome: 'Contractual blocker removed ahead of the close window' },
    { id: 'vx-fu-5', priority: 'Medium', action: 'Bring Piotr Nowak into the next commercial session', owner: 'Mike Johnson', timing: 'Next meeting', reason: 'Seven of eight interactions involve one person.', expectedOutcome: 'Reduced single-threading risk' },
  ],

  suggestedEmail: {
    subject: 'Predictive Maintenance — before the 14 August lock',
    body:
      'Hi Thomas,\n\nWe spoke on 24 July and I have been conscious of not adding noise since. But with the budget lock on the 14th, I would rather ask a direct question than assume.\n\nIs there a realistic path to a decision before that date? If there is, the fastest route is a short conversation with Anneliese — I can cover the total cost position, how we compare with the alternative you mentioned, and what would have to happen operationally to start in September.\n\nIf there is not, that is genuinely fine — but I would like to reset the timeline honestly with you rather than carry a date that neither of us believes.\n\nCould you let me know either way this week?\n\nBest regards,\nMike Johnson',
  },

  callScript: [
    { label: 'Opening', lines: ['"Hi Thomas — I know it has been a couple of weeks, so I will be direct."', '"I have one question about timing, and I would rather ask it than guess."'] },
    { label: 'Context', lines: ['"When we spoke on the 24th, two things came up: the budget lock on the 14th, and the alternative you are looking at."', '"Both of those change how I should be supporting you, so I want to understand where they stand."'] },
    { label: 'Discovery questions', lines: ['"Is a decision before the 14th realistic, or should we be planning around the next cycle?"', '"What is Anneliese’s position on this at the moment?"', '"On the alternative — what specifically looks stronger to them?"', '"Is the liability cap question still open with your legal team?"'] },
    { label: 'Value positioning', lines: ['"The engineering sign-off across both plants is done — that is the part that usually takes longest, and it is behind us."', '"On total cost over three years, including integration, the comparison looks different from the entry price. I would rather show you that than argue it."'] },
    { label: 'Objection handling', lines: ['"If the concern is the capital commitment before the freeze — there are structures that spread year one without changing scope."', '"If the concern is that we are more expensive — let us compare like for like, including what the alternative does not include."', '"If the honest answer is that this slips — tell me, and I will reset the date rather than chase you."'] },
    { label: 'Closing / next step', lines: ['"Can you put me in front of Anneliese for 30 minutes this week?"', '"If not, can we agree today what the realistic close date is, so I stop working to the wrong one?"'] },
  ],

  meetingAgenda: [
    { topic: 'Where the programme stands and what has changed', minutes: 5, objective: 'Establish a shared, current view rather than working from July assumptions', participants: 'Thomas Reinhardt, Mike Johnson' },
    { topic: 'Budget freeze and decision timing', minutes: 10, objective: 'Determine whether a pre-14 August decision is realistic', participants: 'Anneliese Braun, Thomas Reinhardt' },
    { topic: 'Total cost position and competitive comparison', minutes: 10, objective: 'Replace entry-price comparison with a three-year total cost view', participants: 'Anneliese Braun, Mike Johnson' },
    { topic: 'Outstanding legal and integration questions', minutes: 10, objective: 'Close the liability cap question and confirm integration scope', participants: 'Vertex Legal, Piotr Nowak' },
    { topic: 'Agreed close plan with owners and dates', minutes: 5, objective: 'Leave with a written plan or an agreed revised timeline', participants: 'All attendees' },
  ],

  confidence: {
    score: 71,
    tier: 'Moderate Confidence',
    rationale: [
      'Rich interaction history across nine months',
      'Technical validation and stage changes recorded',
      'Competitor and budget-freeze statements captured directly from call notes',
    ],
    uncertainty:
      'No communication in 14 days means the customer’s current internal position is unobserved. The risk assessment may understate or overstate the situation until contact resumes.',
  },

  importantNotes: [
    'AI-generated recommendations should be reviewed against the latest customer context before action.',
    'Win probability of 72% reflects the technical position and has not been adjusted for the 21-day executive gap — treat it as optimistic.',
  ],

  keyTakeaways: [
    'The technical evaluation is won; the commercial process has stalled.',
    'Twenty-one days of CFO silence, not price, is the primary threat to this deal.',
    'The close date is not credible as it stands and should be confirmed or reset this week.',
    'A named competitor has gone unanswered for two weeks — that gap needs closing first.',
  ],
};

/* ------------------------------------------------------------
   Report 3 — Brightpath Healthcare (late stage, high value)
   ------------------------------------------------------------ */

const BRIGHTPATH: AiInsightReport = {
  id: 'insight-brightpath',
  subject: 'Brightpath Healthcare',
  headline:
    'Largest opportunity in the current period, commercially agreed and in contract review. Remaining risk is scheduling rather than substance.',
  primaryRecommendation: 'Confirm the procurement committee date with legal counsel this week',
  topRisk: 'Redlines returned nine days ago remain unacknowledged with no committee date set',

  customerSummary: {
    company: 'Brightpath Healthcare',
    primaryContact: 'Grace Whitfield',
    contactTitle: 'Chief Nursing Informatics Officer',
    industry: 'Healthcare',
    relationshipStage: 'Existing account — multi-site expansion',
    accountOwner: 'Ana Ruiz',
    lastInteraction: '2026-07-29',
    opportunity: 'Care Coordination Suite — 3 Hospitals',
    opportunityValue: 1150000,
    expectedCloseDate: '2026-08-28',
    narrative:
      'Brightpath has been a customer for two years at a single site. This opportunity extends the platform to three hospitals and represents the largest single expansion in the current pipeline. Clinical and operational stakeholders are fully aligned, and commercial terms were agreed in mid-July. The master services agreement has been through one round of redlines, returned to the customer on 29 July. The remaining path is procedural: the board procurement committee must ratify the agreement, and no meeting date has been confirmed.',
  },

  relationshipScore: {
    score: 86,
    tier: 'Strong',
    rationale:
      'Two years of delivery history, a clinical champion with board access and consistent multi-stakeholder engagement. The only weak point is a procurement function that engages late by design.',
    factors: [
      { label: 'Communication recency', value: 79, note: 'Last two-way exchange 9 days ago' },
      { label: 'Response rate', value: 91, note: 'Consistently answered within two working days' },
      { label: 'Meeting engagement', value: 94, note: 'Twelve meetings across clinical, legal and operations' },
      { label: 'Decision-maker access', value: 88, note: 'Direct contact with general counsel and procurement' },
      { label: 'Proposal activity', value: 82, note: 'MSA and pricing schedule both reviewed in detail' },
    ],
  },

  buyingSignals: [
    { id: 'bp-sig-1', signal: 'Redlines returned with commercial terms accepted', date: '2026-07-29', strength: 'Strong', explanation: 'Legal engaged substantively on liability and data terms only — pricing was not reopened.' },
    { id: 'bp-sig-2', signal: 'Implementation timeline requested for all three sites', date: '2026-07-25', strength: 'Strong', explanation: 'Operations has begun sequencing site readiness, which only happens when a decision is assumed.' },
    { id: 'bp-sig-3', signal: 'Multiple stakeholders engaged', date: '2026-07-21', strength: 'Moderate', explanation: 'Clinical, legal, procurement and IT have all participated in the last month.' },
    { id: 'bp-sig-4', signal: 'Reference request from a peer trust', date: '2026-07-16', strength: 'Moderate', explanation: 'Grace introduced a counterpart at another organisation — advocacy behaviour, not evaluation behaviour.' },
  ],

  salesHealth: {
    dealHealth: 'Watch',
    winProbability: 88,
    momentum: 'Steady',
    daysInStage: 14,
    nextMilestone: 'Procurement committee ratification',
    targetCloseDate: '2026-08-28',
    note: 'Health is "Watch" rather than "Healthy" only because the committee date is unknown and the close date is 21 days away.',
  },

  pipelinePosition: {
    currentStage: 'Contract Review',
    stageOrder: STAGE_ORDER,
    pipelineHealth: 'Strong — in line with comparable expansions',
    averageStageDays: 16,
    note: 'One stage remains. Comparable healthcare expansions completed contract review in 16 days once a committee date was fixed.',
  },

  risks: [
    { id: 'bp-risk-1', severity: 'Medium', risk: 'Procurement approval timeline unclear', evidence: 'Redlines returned 29 July; receipt acknowledged but no committee date committed.', impact: 'A 21-day close window depends on a meeting that may not be scheduled', mitigation: 'Ask counsel directly for the committee calendar and the submission cut-off' },
    { id: 'bp-risk-2', severity: 'Low', risk: 'Site readiness varies across the three hospitals', evidence: 'Operations flagged that the third site has an unrelated system migration in Q4.', impact: 'Phase three delivery may slip, affecting recognised revenue timing', mitigation: 'Sequence the third site last in the implementation schedule' },
    { id: 'bp-risk-3', severity: 'Low', risk: 'Champion dependency at board level', evidence: 'Board visibility runs entirely through Grace Whitfield.', impact: 'Limited fallback if the champion is unavailable during the approval window', mitigation: 'Establish a direct line with the procurement director before submission' },
  ],

  activities: [
    { id: 'bp-act-1', type: 'document', title: 'Marked-up MSA returned to customer counsel', detail: 'All commercial redlines addressed', date: '2026-07-29' },
    { id: 'bp-act-2', type: 'meeting', title: 'Implementation planning — three sites', detail: 'Site sequencing discussed; Q4 migration flagged at site three', date: '2026-07-25' },
    { id: 'bp-act-3', type: 'meeting', title: 'Legal review call', detail: 'Liability and data processing terms agreed in principle', date: '2026-07-21' },
    { id: 'bp-act-4', type: 'email', title: 'Reference introduction from Grace Whitfield', detail: 'Introduced a counterpart at a peer organisation', date: '2026-07-16' },
    { id: 'bp-act-5', type: 'stage', title: 'Stage updated to Contract Review', detail: 'Moved by Ana Ruiz after commercial agreement', date: '2026-07-14' },
    { id: 'bp-act-6', type: 'proposal', title: 'Commercial terms accepted', detail: 'Three-site pricing schedule agreed', date: '2026-07-13' },
  ],

  communication: {
    lastCommunication: '2026-07-29',
    responseTrend: 'Stable — consistent two-working-day turnaround throughout',
    averageResponseHours: 31,
    engagementLevel: 'Moderate',
    sentiment: 'Positive',
    openQuestions: [
      'When does the procurement committee next meet?',
      'What is the submission cut-off for committee papers?',
      'Can site three be sequenced after the Q4 migration?',
    ],
    currentGapDays: 9,
  },

  decisionMakers: [
    { id: 'bp-dm-1', name: 'Grace Whitfield', role: 'Chief Nursing Informatics Officer', buyingRole: 'Champion', influence: 'High', engagement: 'High', relationship: 'Strong', keyConcern: 'Clinical continuity during a three-site rollout' },
    { id: 'bp-dm-2', name: 'Warren Castillo', role: 'General Counsel', buyingRole: 'Decision Maker', influence: 'High', engagement: 'Moderate', relationship: 'Developing', keyConcern: 'Data processing terms across three legal entities' },
    { id: 'bp-dm-3', name: 'Dolores Kim', role: 'Director of Procurement', buyingRole: 'Procurement', influence: 'High', engagement: 'Moderate', relationship: 'Developing', keyConcern: 'Committee submission requirements and timing' },
    { id: 'bp-dm-4', name: 'Site 3 Operations', role: 'Head of Operations', buyingRole: 'Influencer', influence: 'Medium', engagement: 'Low', relationship: 'Weak', keyConcern: 'Capacity to absorb a rollout alongside a Q4 migration' },
  ],

  opportunities: [
    { id: 'bp-opp-1', name: 'Care Coordination Suite — 3 Hospitals', stage: 'Contract Review', value: 1150000, probability: 88, expectedCloseDate: '2026-08-28', nextMilestone: 'Procurement committee ratification', health: 'Watch' },
    { id: 'bp-opp-2', name: 'Analytics Module — Existing Site', stage: 'Proposal', value: 185000, probability: 55, expectedCloseDate: '2026-10-16', nextMilestone: 'Clinical business case review', health: 'Healthy' },
    { id: 'bp-opp-3', name: 'Managed Services — Year 1', stage: 'Qualification', value: 96000, probability: 25, expectedCloseDate: '2026-12-04', nextMilestone: 'Raise at the 30-day post-signature review', health: 'Watch' },
  ],

  followUps: [
    { id: 'bp-fu-1', priority: 'High', action: 'Ask Warren Castillo directly for the committee date and paper cut-off', owner: 'Ana Ruiz', timing: 'By 10 Aug', reason: 'The close date depends entirely on a meeting whose date is unknown.', expectedOutcome: 'Forecastable close date backed by a calendared decision point' },
    { id: 'bp-fu-2', priority: 'High', action: 'Establish a direct line with Dolores Kim ahead of submission', owner: 'Ana Ruiz', timing: 'This week', reason: 'All board visibility currently runs through the clinical champion.', expectedOutcome: 'Second route into the approval process' },
    { id: 'bp-fu-3', priority: 'Medium', action: 'Confirm the implementation sequence with site three placed last', owner: 'Ana Ruiz', timing: 'Before signature', reason: 'A Q4 system migration at site three could delay phase three delivery.', expectedOutcome: 'Delivery plan that survives contact with the customer’s Q4 calendar' },
    { id: 'bp-fu-4', priority: 'Low', action: 'Prepare the managed services conversation for the 30-day review', owner: 'Ana Ruiz', timing: 'Post-signature', reason: 'Adoption reviews are the highest-converting expansion moment in this segment.', expectedOutcome: 'Qualified expansion opportunity without a new procurement cycle' },
  ],

  suggestedEmail: {
    subject: 'Care Coordination Suite — committee timing',
    body:
      'Hi Warren,\n\nThank you for turning the agreement around as quickly as you did — the redlines were clear and we have addressed all of them in the version returned on 29 July.\n\nOne practical question: when does the procurement committee next meet, and what is the cut-off for submitting papers? We are working to a late-August start for site one, and the sequencing depends on that date rather than on anything outstanding between us.\n\nIf it is helpful, I can prepare a one-page summary in whatever format the committee prefers.\n\nBest regards,\nAna Ruiz',
  },

  callScript: [
    { label: 'Opening', lines: ['"Hi Grace, thank you again for the introduction to your counterpart — that was generous."', '"I have one practical thing to sort out, and it is procedural rather than commercial."'] },
    { label: 'Context', lines: ['"The agreement went back to Warren on the 29th with all redlines addressed."', '"Everything substantive is agreed. What we do not have is a committee date."'] },
    { label: 'Discovery questions', lines: ['"Do you know when the procurement committee next sits?"', '"Is there a paper submission deadline we should be working back from?"', '"Is there anything the committee will want to see that we have not provided?"'] },
    { label: 'Value positioning', lines: ['"Site one is ready to start in late August, and the clinical team has already sequenced readiness."', '"Every week of delay pushes the first site’s benefit into the next quarter."'] },
    { label: 'Objection handling', lines: ['"If the committee calendar is fixed and late — we can start implementation planning in parallel at no cost to you."', '"If additional documentation is needed — tell me the format and I will have it within two days."'] },
    { label: 'Closing / next step', lines: ['"Could you or Warren confirm the committee date this week?"', '"Once I have that, I will work everything else backwards from it and stop asking."'] },
  ],

  meetingAgenda: [
    { topic: 'Agreement status and outstanding items', minutes: 5, objective: 'Confirm nothing substantive remains open', participants: 'Warren Castillo, Ana Ruiz' },
    { topic: 'Committee timing and submission requirements', minutes: 10, objective: 'Fix a date and a documentation format', participants: 'Dolores Kim, Warren Castillo' },
    { topic: 'Implementation sequencing across three sites', minutes: 10, objective: 'Agree the order and place site three after the Q4 migration', participants: 'Grace Whitfield, site operations' },
    { topic: 'Clinical readiness and change support', minutes: 10, objective: 'Confirm training and cutover support per site', participants: 'Grace Whitfield, delivery lead' },
    { topic: 'Agreed next steps and owners', minutes: 5, objective: 'Leave with a committee date and named owners', participants: 'All attendees' },
  ],

  confidence: {
    score: 82,
    tier: 'High Confidence',
    rationale: [
      'Two years of account history available',
      'Twelve stakeholder interactions across four functions',
      'Contract and pricing engagement recorded in detail',
      'Champion advocacy behaviour observed externally',
    ],
    uncertainty:
      'The committee calendar is external to the CRM and cannot be inferred. The close date carries scheduling risk that this analysis cannot quantify.',
  },

  importantNotes: [
    'AI-generated recommendations should be reviewed against the latest customer context before action.',
    'Revenue recognition timing depends on site sequencing and may differ from the contract value shown.',
  ],

  keyTakeaways: [
    'Commercially agreed — the remaining path is procedural, not persuasive.',
    'The close date rests on a committee meeting whose date nobody has confirmed.',
    'Champion advocacy is unusually strong and worth protecting with a second procurement contact.',
    'Best next action is a direct request to counsel for the committee calendar this week.',
  ],
};

export const INSIGHT_REPORTS: AiInsightReport[] = [NORTHWIND, VERTEX, BRIGHTPATH];

/* ------------------------------------------------------------
   Query resolution index
   Maps entity names and analytical intents onto a report. Intent
   queries carry a note explaining which account was selected and
   why, so the focus of the answer is never implicit.
   ------------------------------------------------------------ */

export interface QueryRoute {
  keywords: string[];
  reportId: string;
  focusNote: string | null;
}

export const QUERY_ROUTES: QueryRoute[] = [
  { keywords: ['northwind', 'fleet visibility', 'meera', 'krishnan', 'logistics'], reportId: 'insight-northwind', focusNote: null },
  { keywords: ['vertex', 'predictive maintenance', 'thomas', 'reinhardt', 'manufacturing'], reportId: 'insight-vertex', focusNote: null },
  { keywords: ['brightpath', 'care coordination', 'grace', 'whitfield', 'healthcare'], reportId: 'insight-brightpath', focusNote: null },
  {
    keywords: ['at risk', 'risk', 'deals at risk', 'attention', 'need attention', 'slipping', 'stalled', 'cold', 'gone cold', 'no response'],
    reportId: 'insight-vertex',
    focusNote:
      'Five opportunities currently carry high or critical risk. Focused on Vertex Manufacturing — the largest exposure at $725,000 with a close date inside nine days.',
  },
  {
    keywords: ['pipeline health', 'pipeline', 'forecast', 'health'],
    reportId: 'insight-northwind',
    focusNote:
      'Portfolio-level analytics are shown in the Sales Intelligence Snapshot below. Account view focused on Northwind Logistics — the largest active proposal in the current period.',
  },
  {
    keywords: ['closing this month', 'high-value', 'high value', 'weekly', 'weekly summary', 'sales summary', 'largest', 'biggest'],
    reportId: 'insight-brightpath',
    focusNote:
      'Focused on Brightpath Healthcare — the largest opportunity closing in the current period at $1,150,000.',
  },
];

export const NO_MATCH_SUGGESTIONS: string[] = [
  'Summarize Northwind Logistics',
  'Which deals are at risk?',
  'Show high-value deals closing this month',
];

/* ------------------------------------------------------------
   Sales Intelligence Snapshot
   Pipeline figures are derived from the Next Best Action dataset
   so the two pages never disagree. Forecast, funnel and velocity
   series are curated demonstration data.
   ------------------------------------------------------------ */

const OPEN_STAGES: OpportunityStage[] = [
  'Qualification',
  'Discovery',
  'Proposal',
  'Negotiation',
  'Contract Review',
];

export function buildSalesIntelligenceSnapshot(): SalesIntelligenceSnapshot {
  const open = NBA_RECORDS.filter(record => OPEN_STAGES.includes(record.stage));

  const pipelineValue = open.reduce((total, record) => total + record.expectedRevenue, 0);
  const weighted = open.reduce(
    (total, record) => total + (record.expectedRevenue * record.winProbability) / 100,
    0,
  );
  const atRisk = open.filter(record => record.dealRisk === 'High' || record.dealRisk === 'Critical');
  const averageConfidence =
    NBA_RECORDS.reduce((total, record) => total + record.confidence, 0) / NBA_RECORDS.length;

  const pipelineByStage: SeriesPoint[] = OPEN_STAGES.map(stage => ({
    label: stage,
    value: open
      .filter(record => record.stage === stage)
      .reduce((total, record) => total + record.expectedRevenue, 0),
  }));

  // Grouped by deal-size band rather than industry: the working set spans
  // more than twenty industries, which fragments a donut into noise.
  const BANDS: { label: string; min: number; max: number }[] = [
    { label: 'Under $250K', min: 0, max: 250_000 },
    { label: '$250K – $500K', min: 250_000, max: 500_000 },
    { label: '$500K – $750K', min: 500_000, max: 750_000 },
    { label: '$750K and above', min: 750_000, max: Number.POSITIVE_INFINITY },
  ];

  const opportunityDistribution: SeriesPoint[] = BANDS.map(band => ({
    label: band.label,
    value: open
      .filter(record => record.expectedRevenue >= band.min && record.expectedRevenue < band.max)
      .reduce((total, record) => total + record.expectedRevenue, 0),
  }));

  return {
    kpis: [
      {
        id: 'open-pipeline',
        label: 'Open Pipeline',
        value: `$${(pipelineValue / 1_000_000).toFixed(2)}M`,
        delta: `${open.length} active opportunities`,
        trend: 'up',
      },
      {
        id: 'weighted',
        label: 'Weighted Forecast',
        value: `$${(weighted / 1_000_000).toFixed(2)}M`,
        delta: 'Probability-adjusted',
        trend: 'up',
      },
      {
        id: 'at-risk',
        label: 'Value At Risk',
        value: `$${(atRisk.reduce((t, r) => t + r.expectedRevenue, 0) / 1_000_000).toFixed(2)}M`,
        delta: `${atRisk.length} opportunities flagged`,
        trend: 'down',
      },
      {
        id: 'confidence',
        label: 'Avg AI Confidence',
        value: `${Math.round(averageConfidence)}%`,
        delta: 'Across all recommendations',
        trend: 'flat',
      },
    ],
    pipelineByStage,
    revenueForecast: [
      { label: 'Mar', value: 1.42, compare: 1.38 },
      { label: 'Apr', value: 1.61, compare: 1.55 },
      { label: 'May', value: 1.48, compare: 1.62 },
      { label: 'Jun', value: 1.87, compare: 1.79 },
      { label: 'Jul', value: 2.04, compare: 1.94 },
      { label: 'Aug', value: 2.31, compare: 2.12 },
    ],
    conversionFunnel: [
      { label: 'Leads', count: 412, value: 8_240_000 },
      { label: 'Qualified', count: 186, value: 5_120_000 },
      { label: 'Discovery', count: 98, value: 3_640_000 },
      { label: 'Proposal', count: 54, value: 2_480_000 },
      { label: 'Negotiation', count: 31, value: 1_720_000 },
      { label: 'Closed Won', count: 19, value: 1_090_000 },
    ],
    opportunityDistribution,
    dealVelocityDays: [
      { label: 'Qualification', value: 11 },
      { label: 'Discovery', value: 18 },
      { label: 'Proposal', value: 19 },
      { label: 'Negotiation', value: 24 },
      { label: 'Contract Review', value: 16 },
    ],
  };
}
