/**
 * AI Insights (Checkpoint 7) — types and API access.
 *
 * Mirrors `backend/app/products/crm/ai_insights/schemas.py` and its router.
 * Every function here hits the real API; nothing under `features/ai/insights`
 * or `features/ai/next-best-action` (the pre-Checkpoint-7 fixtures) is
 * imported.
 */

import { api } from '@/lib/api-client';

/* ------------------------------------------------------------------
   Types
   ------------------------------------------------------------------ */

export type AiFeature =
  | 'ACCOUNT_SUMMARY'
  | 'ACCOUNT_INTELLIGENCE'
  | 'OPPORTUNITY_SUMMARY'
  | 'LEAD_SUMMARY'
  | 'NEXT_BEST_ACTION'
  | 'EMAIL_DRAFT'
  | 'MEETING_EXTRACTION'
  | 'NL_QUERY'
  | 'PRIORITIZATION_EXPLANATION';

export type AiGenerationStatus = 'READY' | 'FAILED';
export type AiFeedbackRating = 'UP' | 'DOWN';

export interface AiGeneration {
  id: string;
  feature: AiFeature;
  entity_type: string | null;
  entity_id: string | null;
  status: AiGenerationStatus;
  model: string | null;
  error_code: string | null;
  content: Record<string, unknown>;
  used_crm_context: boolean;
  created_by_id: string | null;
  created_at: string;
  feedback_rating: AiFeedbackRating | null;
  feedback_comment: string | null;
  feedback_at: string | null;
}

export interface RecordSummaryContent {
  summary: string;
}

export interface RelationshipHealth {
  status: 'HEALTHY' | 'AT_RISK' | 'UNKNOWN';
  rationale: string;
}

export interface AccountIntelligenceContent {
  summary: string;
  relationship_health: RelationshipHealth;
  risks: string[];
  opportunities: string[];
  recommended_actions: string[];
  missing_information: string[];
}

export interface NextBestActionContent {
  action: string;
  why: string;
  urgency: 'HIGH' | 'MEDIUM' | 'LOW';
  evidence: string[];
  suggested_actions: string[];
}

export interface EmailDraftContent {
  subject: string;
  body: string;
}

export type EmailDraftTone = 'PROFESSIONAL' | 'FRIENDLY' | 'CONCISE' | 'FORMAL';

export interface EmailDraftRequest {
  contact_id?: string | null;
  account_id?: string | null;
  opportunity_id?: string | null;
  lead_id?: string | null;
  tone?: EmailDraftTone;
  instruction: string;
  previous_draft?: string | null;
}

export interface MeetingActionItem {
  kind: 'TASK' | 'NOTE' | 'OPPORTUNITY_AMOUNT';
  description: string;
  amount: string | null;
}

export interface MeetingExtractionContent {
  summary: string;
  participants: string[];
  key_points: string[];
  requirements: string[];
  objections: string[];
  commitments: string[];
  sentiment: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | 'MIXED' | 'UNKNOWN';
  follow_up_actions: MeetingActionItem[];
  /** Indexes into `follow_up_actions` already created — added after apply. */
  applied_indexes?: number[];
}

export interface MeetingAppliedItem {
  index: number;
  kind: string;
  description: string;
  outcome: 'CREATED' | 'SKIPPED' | 'FAILED';
  reason: string | null;
  entity_type: string | null;
  entity_id: string | null;
}

export interface PriorityReason {
  label: string;
  detail: string;
}

/**
 * Plain CRM fields about a ranked record, for display beside its reasons.
 * Fields that do not apply to the record's type are `null`.
 */
export interface PriorityRecordFacts {
  /* Opportunities */
  account_id: string | null;
  /** `null` when the caller may see the deal but not its account. */
  account_name: string | null;
  stage_name: string | null;
  deal_value: string | null;
  currency: string | null;
  win_probability: number | null;
  expected_close_date: string | null;
  /* Leads */
  company: string | null;
  email: string | null;
  phone: string | null;
  status: string | null;
  expected_deal_size: string | null;
  /* Both */
  last_activity_at: string | null;
  open_task_count: number;
  overdue_task_count: number;
}

export type NbaCategory = 'COMMUNICATION' | 'MEETING' | 'CONTENT' | 'INTERNAL' | 'QUALIFICATION' | 'RISK';
export type NbaExecution = 'EMAIL' | 'CALL' | 'WHATSAPP' | 'LINKEDIN' | 'MEETING' | 'TASK' | 'NOTE' | 'RECORD';
export type CopilotKind = 'EMAIL' | 'MESSAGE' | 'MEETING_AGENDA' | 'CALL_SCRIPT' | 'PROPOSAL';
export type NbaRecordKind = 'OPPORTUNITY' | 'LEAD';

export interface NbaSignalEvidence {
  key: string;
  label: string;
  value: string;
}

/** One recommended action from the Next Best Action engine. */
export interface NbaAction {
  action_code: string;
  category: NbaCategory;
  label: string;
  execution: NbaExecution;
  copilot: CopilotKind | null;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  /** RULE = Level 1 rules engine; PREDICTIVE = Level 2 similar-deal history. */
  level: 'RULE' | 'PREDICTIVE';
  reasons: string[];
  rule_keys: string[];
  signals: NbaSignalEvidence[];
  timing: string | null;
  due_at: string | null;
  /** 0–100, only where it is measured (predictive). */
  confidence: number | null;
}

export interface PriorityScore {
  entity_type: NbaRecordKind;
  entity_id: string;
  entity_label: string;
  level: 'HIGH' | 'MEDIUM' | 'LOW';
  score: number;
  reasons: PriorityReason[];
  facts: PriorityRecordFacts;
  /** The most recent cached Next Best Action, if one was ever generated. */
  latest_recommendation: AiGeneration | null;
  /** The engine's recommended actions, best first — no model call. */
  actions: NbaAction[];
  /** The signal snapshot the actions were computed from. */
  signals: Record<string, string | number | boolean | null>;
}

export interface NbaCatalog {
  categories: NbaCategory[];
  actions: {
    code: string;
    category: NbaCategory;
    label: string;
    execution: NbaExecution;
    copilot: CopilotKind | null;
    applies_to: NbaRecordKind[];
  }[];
  signals: { key: string; label: string; kind: string; applies_to: NbaRecordKind[]; source: string }[];
  operators: string[];
}

export interface NbaCondition {
  field_key: string;
  operator: string;
  value: unknown;
}

export interface NbaRule {
  key: string;
  id: string | null;
  source: 'BUILTIN' | 'CUSTOM';
  name: string;
  description: string | null;
  applies_to: NbaRecordKind | 'BOTH';
  logic: 'AND' | 'OR';
  conditions: NbaCondition[];
  action_code: string;
  action_label: string;
  category: NbaCategory | '';
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  reason: string;
  timing: string | null;
  due_in_hours: number | null;
  cooldown_days: number;
  is_active: boolean;
  is_overridden: boolean;
}

export interface NbaRuleInput {
  name: string;
  description?: string | null;
  applies_to: NbaRecordKind | 'BOTH';
  logic: 'AND' | 'OR';
  conditions: NbaCondition[];
  action_code: string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  reason: string;
  timing?: string | null;
  due_in_hours?: number | null;
  cooldown_days?: number;
  is_active?: boolean;
}

export interface CopilotEmailContent {
  kind: 'EMAIL';
  action_code: string;
  subject: string;
  body: string;
}
export interface CopilotMessageContent {
  kind: 'MESSAGE';
  action_code: string;
  body: string;
}
export interface CopilotMeetingContent {
  kind: 'MEETING_AGENDA';
  action_code: string;
  title: string;
  duration_minutes: number;
  description: string;
  agenda: { topic: string; minutes: number; objective: string }[];
  attendee_roles: string[];
}
export interface CopilotCallScriptContent {
  kind: 'CALL_SCRIPT';
  action_code: string;
  opening: string;
  questions: string[];
  talking_points: string[];
  objections: { objection: string; response: string }[];
  close: string;
}
export interface CopilotProposalContent {
  kind: 'PROPOSAL';
  action_code: string;
  summary: string;
  sections: { title: string; content: string }[];
  next_steps: string[];
}
export type CopilotContent =
  | CopilotEmailContent
  | CopilotMessageContent
  | CopilotMeetingContent
  | CopilotCallScriptContent
  | CopilotProposalContent;

export interface InsightItem {
  kind: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  title: string;
  detail: string;
  entity_type: string;
  entity_id: string;
  entity_label: string;
}

export interface InsightsDigest {
  generated_at: string;
  deals_at_risk: InsightItem[];
  stale_opportunities: InsightItem[];
  neglected_leads: InsightItem[];
  accounts_needing_attention: InsightItem[];
  overdue_tasks: InsightItem[];
}

export interface NlQueryResponse {
  generation_id: string;
  understood: boolean;
  clarification: string | null;
  definition: Record<string, unknown> | null;
  result: {
    name: string;
    columns: { key: string; label: string; type: string }[];
    rows: Record<string, unknown>[];
    row_limit_reached: boolean;
  } | null;
}

/* ------------------------------------------------------------------
   Summaries & Account Intelligence
   ------------------------------------------------------------------ */

const BASE = '/crm/ai-insights';

export const getAccountSummary = (accountId: string) =>
  api.get<AiGeneration | null>(`${BASE}/accounts/${accountId}/summary`);
export const generateAccountSummary = (accountId: string) =>
  api.post<AiGeneration>(`${BASE}/accounts/${accountId}/summary`);

export const getAccountIntelligence = (accountId: string) =>
  api.get<AiGeneration | null>(`${BASE}/accounts/${accountId}/intelligence`);
export const generateAccountIntelligence = (accountId: string) =>
  api.post<AiGeneration>(`${BASE}/accounts/${accountId}/intelligence`);

export const getOpportunitySummary = (opportunityId: string) =>
  api.get<AiGeneration | null>(`${BASE}/opportunities/${opportunityId}/summary`);
export const generateOpportunitySummary = (opportunityId: string) =>
  api.post<AiGeneration>(`${BASE}/opportunities/${opportunityId}/summary`);

export const getLeadSummary = (leadId: string) =>
  api.get<AiGeneration | null>(`${BASE}/leads/${leadId}/summary`);
export const generateLeadSummary = (leadId: string) =>
  api.post<AiGeneration>(`${BASE}/leads/${leadId}/summary`);

/* ------------------------------------------------------------------
   Next Best Action
   ------------------------------------------------------------------ */

export const getOpportunityNextBestAction = (opportunityId: string) =>
  api.get<AiGeneration | null>(`${BASE}/opportunities/${opportunityId}/next-best-action`);
export const generateOpportunityNextBestAction = (opportunityId: string) =>
  api.post<AiGeneration>(`${BASE}/opportunities/${opportunityId}/next-best-action`);

export const getLeadNextBestAction = (leadId: string) =>
  api.get<AiGeneration | null>(`${BASE}/leads/${leadId}/next-best-action`);
export const generateLeadNextBestAction = (leadId: string) =>
  api.post<AiGeneration>(`${BASE}/leads/${leadId}/next-best-action`);

/* ------------------------------------------------------------------
   AI email assistant
   ------------------------------------------------------------------ */

export const draftEmail = (request: EmailDraftRequest) =>
  api.post<AiGeneration>(`${BASE}/email-draft`, request);

/* ------------------------------------------------------------------
   Meeting-to-CRM
   ------------------------------------------------------------------ */

export const extractMeeting = (payload: {
  text: string;
  account_id?: string | null;
  opportunity_id?: string | null;
}) => api.post<AiGeneration>(`${BASE}/meetings/extract`, payload);

export const applyMeetingActions = (generationId: string, indexes: number[]) =>
  api.post<{ generation: AiGeneration; results: MeetingAppliedItem[] }>(
    `${BASE}/meetings/${generationId}/apply`,
    { indexes },
  );

/* ------------------------------------------------------------------
   Natural-language CRM queries
   ------------------------------------------------------------------ */

export const runNlQuery = (question: string) =>
  api.post<NlQueryResponse>(`${BASE}/query`, { question });

/* ------------------------------------------------------------------
   Prioritization — rules first, AI explanation second
   ------------------------------------------------------------------ */

export const priorityOpportunities = (limit = 25) =>
  api.get<{ items: PriorityScore[] }>(`${BASE}/priority/opportunities?limit=${limit}`);
export const priorityLeads = (limit = 25) =>
  api.get<{ items: PriorityScore[] }>(`${BASE}/priority/leads?limit=${limit}`);
export const explainOpportunityPriority = (opportunityId: string) =>
  api.post<AiGeneration>(`${BASE}/priority/opportunities/${opportunityId}/explain`);
export const explainLeadPriority = (leadId: string) =>
  api.post<AiGeneration>(`${BASE}/priority/leads/${leadId}/explain`);

/* ------------------------------------------------------------------
   Next Best Action engine — rules, history, Copilot
   ------------------------------------------------------------------ */

const NBA = `${BASE}/nba`;

export const getNbaCatalog = () => api.get<NbaCatalog>(`${NBA}/catalog`);
export const nbaForRecord = (kind: NbaRecordKind, id: string) =>
  api.get<PriorityScore | null>(`${NBA}/${kind === 'OPPORTUNITY' ? 'opportunities' : 'leads'}/${id}`);

export const listNbaRules = () => api.get<NbaRule[]>(`${NBA}/rules`);
export const createNbaRule = (body: NbaRuleInput) => api.post<NbaRule>(`${NBA}/rules`, body);
export const updateNbaRule = (id: string, body: Partial<NbaRuleInput>) =>
  api.patch<NbaRule>(`${NBA}/rules/${id}`, body);
export const deleteNbaRule = (id: string) => api.delete<void>(`${NBA}/rules/${id}`);
export const overrideBuiltinRule = (
  key: string,
  body: {
    is_active?: boolean;
    priority?: 'HIGH' | 'MEDIUM' | 'LOW';
    logic?: 'AND' | 'OR';
    conditions?: NbaCondition[];
    cooldown_days?: number;
  },
) => api.put<NbaRule>(`${NBA}/rules/builtin/${key}`, body);
export const resetBuiltinRule = (key: string) => api.delete<void>(`${NBA}/rules/builtin/${key}`);

export const logNbaAction = (body: {
  entity_type: NbaRecordKind;
  entity_id: string;
  action_code: string;
  outcome: 'EXECUTED' | 'DISMISSED';
  rule_keys?: string[];
  generation_id?: string | null;
  note?: string | null;
}) => api.post<{ id: string }>(`${NBA}/actions/log`, body);

export const runNbaCopilot = (body: {
  entity_type: NbaRecordKind;
  entity_id: string;
  action_code: string;
  kind?: CopilotKind;
  instruction?: string | null;
}) => api.post<AiGeneration>(`${NBA}/copilot`, body);

/* ------------------------------------------------------------------
   Insights digest (rules only, no model call)
   ------------------------------------------------------------------ */

export const getInsightsDigest = () => api.get<InsightsDigest>(`${BASE}/digest`);

/* ------------------------------------------------------------------
   Feedback and history
   ------------------------------------------------------------------ */

export const submitAiFeedback = (
  generationId: string,
  rating: AiFeedbackRating,
  comment?: string | null,
) => api.post<AiGeneration>(`${BASE}/generations/${generationId}/feedback`, { rating, comment });

export const getAiHistory = (entityType: string, entityId: string) =>
  api.get<AiGeneration[]>(`${BASE}/${entityType}/${entityId}/history`);
