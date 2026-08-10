import type {
  AgendaItem,
  CallScriptSection,
  DealMomentum,
  EmailDraft,
  NbaPriority,
  OpportunityStage,
  RiskItem,
  Stakeholder,
} from '@/features/ai/next-best-action/types';

/* ============================================================
   AI INSIGHTS — TYPES
   Shared intelligence shapes (stakeholders, risks, agendas,
   scripts) are reused from the Next Best Action module rather
   than redefined, so both surfaces stay consistent.
   ============================================================ */

export type RelationshipTier = 'Strong' | 'Healthy' | 'Moderate' | 'Weak' | 'At Risk';
export type SignalStrength = 'Strong' | 'Moderate' | 'Emerging';
export type ConfidenceTier = 'High Confidence' | 'Moderate Confidence' | 'Low Confidence';
export type SentimentTone = 'Positive' | 'Neutral' | 'Mixed' | 'Negative';
export type DealHealth = 'Healthy' | 'Watch' | 'At Risk' | 'Critical';

export interface CustomerSummary {
  company: string;
  primaryContact: string;
  contactTitle: string;
  industry: string;
  relationshipStage: string;
  accountOwner: string;
  lastInteraction: string;
  opportunity: string;
  opportunityValue: number;
  expectedCloseDate: string;
  narrative: string;
}

export interface RelationshipScore {
  score: number;
  tier: RelationshipTier;
  rationale: string;
  factors: { label: string; value: number; note: string }[];
}

export interface BuyingSignal {
  id: string;
  signal: string;
  date: string;
  strength: SignalStrength;
  explanation: string;
}

export interface SalesHealth {
  dealHealth: DealHealth;
  winProbability: number;
  momentum: DealMomentum;
  daysInStage: number;
  nextMilestone: string;
  targetCloseDate: string;
  note: string;
}

export interface PipelinePosition {
  currentStage: OpportunityStage;
  stageOrder: OpportunityStage[];
  pipelineHealth: string;
  averageStageDays: number;
  note: string;
}

export interface ActivityRecord {
  id: string;
  type: 'call' | 'email' | 'meeting' | 'proposal' | 'stage' | 'document' | 'task';
  title: string;
  detail: string;
  date: string;
}

export interface CommunicationSummary {
  lastCommunication: string;
  responseTrend: string;
  averageResponseHours: number;
  engagementLevel: 'High' | 'Moderate' | 'Low';
  sentiment: SentimentTone;
  openQuestions: string[];
  currentGapDays: number;
}

export interface SalesOpportunityRow {
  id: string;
  name: string;
  stage: OpportunityStage;
  value: number;
  probability: number;
  expectedCloseDate: string;
  nextMilestone: string;
  health: DealHealth;
}

export interface FollowUpRecommendation {
  id: string;
  priority: NbaPriority;
  action: string;
  owner: string;
  timing: string;
  reason: string;
  expectedOutcome: string;
}

export interface AiConfidence {
  score: number;
  tier: ConfidenceTier;
  rationale: string[];
  uncertainty: string;
}

/** The complete generated intelligence payload for one query. */
export interface AiInsightReport {
  id: string;
  subject: string;
  headline: string;
  customerSummary: CustomerSummary;
  relationshipScore: RelationshipScore;
  buyingSignals: BuyingSignal[];
  salesHealth: SalesHealth;
  pipelinePosition: PipelinePosition;
  risks: RiskItem[];
  activities: ActivityRecord[];
  communication: CommunicationSummary;
  decisionMakers: Stakeholder[];
  opportunities: SalesOpportunityRow[];
  followUps: FollowUpRecommendation[];
  suggestedEmail: EmailDraft;
  callScript: CallScriptSection[];
  meetingAgenda: AgendaItem[];
  confidence: AiConfidence;
  importantNotes: string[];
  keyTakeaways: string[];
  /** Primary recommendation and top risk, surfaced in the executive summary. */
  primaryRecommendation: string;
  topRisk: string;
}

/** Outcome of a local generation attempt. */
export type AiInsightResult =
  | { status: 'resolved'; report: AiInsightReport; focusNote: string | null }
  | { status: 'no-match'; query: string; suggestions: string[] };

/* ------------------------------------------------------------
   Sales Intelligence Snapshot (portfolio-level analytics)
   ------------------------------------------------------------ */

export interface SnapshotKpi {
  id: string;
  label: string;
  value: string;
  delta: string;
  trend: 'up' | 'down' | 'flat';
}

export interface SeriesPoint {
  label: string;
  value: number;
  /** Optional secondary series value (e.g. forecast vs. actual). */
  compare?: number;
}

export interface FunnelStep {
  label: string;
  count: number;
  value: number;
}

export interface SalesIntelligenceSnapshot {
  kpis: SnapshotKpi[];
  pipelineByStage: SeriesPoint[];
  revenueForecast: SeriesPoint[];
  conversionFunnel: FunnelStep[];
  opportunityDistribution: SeriesPoint[];
  dealVelocityDays: SeriesPoint[];
}
