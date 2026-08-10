/* ============================================================
   NEXT BEST ACTION — TYPES
   Frontend-only intelligence model for the AI module.

   `OpportunityStage` mirrors the stage union already used by the
   Opportunities module so mock records stay compatible with the
   rest of the CRM. Keep the two in sync if stages ever change.
   ============================================================ */

export type OpportunityStage =
  | 'Qualification'
  | 'Discovery'
  | 'Proposal'
  | 'Negotiation'
  | 'Contract Review'
  | 'Closed Won'
  | 'Closed Lost';

export type NbaPriority = 'Critical' | 'High' | 'Medium' | 'Low';

export type NbaStatus =
  | 'New'
  | 'Pending'
  | 'In Progress'
  | 'Scheduled'
  | 'Completed'
  | 'Dismissed';

export type DealRisk = 'Low' | 'Medium' | 'High' | 'Critical';

/** Primary channel the recommended action is executed through. */
export type NbaChannel = 'Meeting' | 'Call' | 'Email' | 'Proposal' | 'Content' | 'Internal';

export type EngagementLevel = 'High' | 'Moderate' | 'Low' | 'Dormant';

export type BuyingRole =
  | 'Champion'
  | 'Decision Maker'
  | 'Influencer'
  | 'Technical Evaluator'
  | 'Procurement'
  | 'Blocker';

export type ProposalStatus =
  | 'Draft'
  | 'Sent'
  | 'Viewed'
  | 'Under Review'
  | 'Revision Requested'
  | 'Approved';

export type SowStatus = 'Not Started' | 'Drafting' | 'Shared' | 'Legal Review' | 'Approved';

export type RiskSeverity = 'Critical' | 'High' | 'Medium' | 'Low';

export type DealMomentum = 'Accelerating' | 'Steady' | 'Slowing' | 'Stalled';

/* ------------------------------------------------------------
   Row-level record — everything the table, KPIs and filters read
   ------------------------------------------------------------ */

export interface NbaRecord {
  id: string;
  leadName: string;
  leadTitle: string;
  company: string;
  industry: string;
  opportunity: string;
  stage: OpportunityStage;
  assignedTo: string;
  priority: NbaPriority;
  /** The recommended action itself — specific and commercially useful. */
  recommendation: string;
  /** Why the engine surfaced it. */
  reason: string;
  channel: NbaChannel;
  /** 0–100 */
  confidence: number;
  previousAction: string;
  previousOutcome: string;
  /** ISO date (yyyy-mm-dd) */
  nextFollowUp: string;
  /** ISO date (yyyy-mm-dd) */
  lastCommunication: string;
  dealRisk: DealRisk;
  /** 0–100 */
  winProbability: number;
  expectedRevenue: number;
  /** ISO date (yyyy-mm-dd) */
  expectedCloseDate: string;
  email: string;
  phone: string;
  leadSource: string;
  engagement: EngagementLevel;
  documents: number;
  status: NbaStatus;
  aiNotes: string;
}

/* ------------------------------------------------------------
   Drawer-level detail
   ------------------------------------------------------------ */

export interface OpportunitySummary {
  name: string;
  stage: OpportunityStage;
  dealSize: number;
  winProbability: number;
  expectedCloseDate: string;
  daysInStage: number;
  lastActivity: string;
  nextMilestone: string;
  momentum: DealMomentum;
}

export interface LeadSummary {
  name: string;
  company: string;
  title: string;
  email: string;
  phone: string;
  leadSource: string;
  owner: string;
  engagement: EngagementLevel;
}

export interface MeetingRecord {
  id: string;
  title: string;
  date: string;
  participants: string[];
  summary: string;
  outcome: string;
  followUpCommitment: string;
}

export interface EmailRecord {
  id: string;
  subject: string;
  date: string;
  direction: 'Inbound' | 'Outbound';
  engagement: 'Opened' | 'Replied' | 'Link Clicked' | 'No Response';
  aiSummary: string;
}

export interface CallRecord {
  id: string;
  date: string;
  salesperson: string;
  durationMinutes: number;
  outcome: string;
  summary: string;
  objection: string;
  followUpAction: string;
}

export type TimelineKind =
  | 'call'
  | 'email'
  | 'meeting'
  | 'proposal'
  | 'stage'
  | 'document'
  | 'ai'
  | 'task';

export interface TimelineEvent {
  id: string;
  kind: TimelineKind;
  title: string;
  detail: string;
  date: string;
}

export interface Stakeholder {
  id: string;
  name: string;
  role: string;
  buyingRole: BuyingRole;
  influence: 'High' | 'Medium' | 'Low';
  engagement: EngagementLevel;
  relationship: 'Strong' | 'Developing' | 'Weak';
  keyConcern: string;
}

export interface EvidenceItem {
  label: string;
  value: string;
}

export interface AiAnalysis {
  rationale: string;
  evidence: EvidenceItem[];
  uncertainty: string;
}

export interface NbaHighlight {
  action: string;
  priority: NbaPriority;
  timing: string;
  owner: string;
  reason: string;
  expectedImpact: string;
  confidence: number;
}

export interface EmailDraft {
  subject: string;
  body: string;
}

export interface CallScriptSection {
  label: string;
  lines: string[];
}

export interface AgendaItem {
  topic: string;
  minutes: number;
  objective: string;
  participants: string;
}

export interface RiskItem {
  id: string;
  severity: RiskSeverity;
  risk: string;
  evidence: string;
  impact: string;
  mitigation: string;
}

export interface CompetitiveNote {
  competitor: string;
  customerConcern: string;
  competitorStrength: string;
  response: string;
}

export interface GrowthPlay {
  offering: string;
  rationale: string;
  estimatedValue: number;
  relevance: 'High' | 'Medium' | 'Low';
  positioning: string;
}

export interface DocumentRef {
  id: string;
  name: string;
  type: 'PDF' | 'DOCX' | 'XLSX' | 'PPTX';
  sizeKb: number;
  sharedOn: string;
  lastViewed: string | null;
}

export interface ProposalState {
  status: ProposalStatus;
  version: string;
  sentOn: string | null;
  lastViewed: string | null;
  value: number;
  note: string;
}

export interface SowState {
  status: SowStatus;
  owner: string;
  targetDate: string | null;
  note: string;
}

export interface NbaDetail {
  recordId: string;
  opportunitySummary: OpportunitySummary;
  leadSummary: LeadSummary;
  meetings: MeetingRecord[];
  emails: EmailRecord[];
  calls: CallRecord[];
  timeline: TimelineEvent[];
  painPoints: string[];
  stakeholders: Stakeholder[];
  aiAnalysis: AiAnalysis;
  highlight: NbaHighlight;
  suggestedEmail: EmailDraft;
  suggestedWhatsapp: string;
  callScript: CallScriptSection[];
  meetingAgenda: AgendaItem[];
  proposal: ProposalState;
  sow: SowState;
  crossSell: GrowthPlay[];
  upsell: GrowthPlay[];
  risks: RiskItem[];
  competitiveNotes: CompetitiveNote[];
  documents: DocumentRef[];
}

/** Alternate recommendation used by the local "Regenerate" demo action. */
export interface RegeneratedRecommendation {
  recommendation: string;
  reason: string;
  confidence: number;
  aiNotes: string;
  priority: NbaPriority;
  channel: NbaChannel;
}
