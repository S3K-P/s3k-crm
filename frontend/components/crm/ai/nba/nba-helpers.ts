import {
  AlertTriangle,
  BookOpen,
  CalendarPlus,
  ClipboardCheck,
  Linkedin,
  ListTodo,
  Mail,
  MessageCircle,
  MessagesSquare,
  NotebookPen,
  Phone,
  SquareArrowOutUpRight,
  Users,
  type LucideIcon,
} from 'lucide-react';

import type { MeterTone } from '@/components/crm/ai/shared/ScoreMeter';
import type { BadgeVariant } from '@/components/crm/shared/StatusBadge';
import type {
  AiGeneration,
  CopilotContent,
  CopilotKind,
  CopilotMeetingContent,
  NbaAction,
  NbaCategory,
  NbaExecution,
  NbaRecordKind,
  PriorityScore,
} from '@/features/ai/ai-insights';
import type {
  DealRisk,
  NbaDetail,
  NbaPriority,
  NbaStatus,
  ProposalStatus,
  RiskSeverity,
  SowStatus,
} from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA ACTION PRESENTATION

   Labels, icons and badge tones for the engine's own vocabulary
   (`ai_insights/nba_catalog.py`). Presentation only — which
   action applies, how urgent it is and why is always the
   backend's answer.
   ============================================================ */

export const CATEGORY_LABEL: Record<NbaCategory, string> = {
  COMMUNICATION: 'Communication',
  MEETING: 'Meeting',
  CONTENT: 'Content',
  INTERNAL: 'Internal',
  QUALIFICATION: 'Qualification',
  RISK: 'Risk',
};

export const CATEGORY_ICON: Record<NbaCategory, LucideIcon> = {
  COMMUNICATION: MessagesSquare,
  MEETING: Users,
  CONTENT: BookOpen,
  INTERNAL: ClipboardCheck,
  QUALIFICATION: ListTodo,
  RISK: AlertTriangle,
};

export const CATEGORY_VARIANT: Record<NbaCategory, BadgeVariant> = {
  COMMUNICATION: 'accent',
  MEETING: 'accent',
  CONTENT: 'neutral',
  INTERNAL: 'neutral',
  QUALIFICATION: 'warning',
  RISK: 'danger',
};

export const PRIORITY_LABEL: Record<NbaAction['priority'], string> = {
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
};

export const PRIORITY_VARIANT: Record<NbaAction['priority'], BadgeVariant> = {
  HIGH: 'danger',
  MEDIUM: 'warning',
  LOW: 'neutral',
};

export const LEVEL_LABEL: Record<NbaAction['level'], string> = {
  RULE: 'Rule-based',
  PREDICTIVE: 'Predictive',
};

/** The button that carries an action out, per execution kind. */
export const EXECUTION_VERB: Record<NbaExecution, string> = {
  EMAIL: 'Compose email',
  CALL: 'Log call',
  WHATSAPP: 'Send WhatsApp',
  LINKEDIN: 'Send LinkedIn message',
  MEETING: 'Schedule meeting',
  TASK: 'Add task',
  NOTE: 'Record note',
  RECORD: 'Open record',
};

export const EXECUTION_ICON: Record<NbaExecution, LucideIcon> = {
  EMAIL: Mail,
  CALL: Phone,
  WHATSAPP: MessageCircle,
  LINKEDIN: Linkedin,
  MEETING: CalendarPlus,
  TASK: ListTodo,
  NOTE: NotebookPen,
  RECORD: SquareArrowOutUpRight,
};

export const COPILOT_LABEL: Record<CopilotKind, string> = {
  EMAIL: 'Draft email',
  MESSAGE: 'Draft message',
  MEETING_AGENDA: 'Draft invite & agenda',
  CALL_SCRIPT: 'Draft call script',
  PROPOSAL: 'Draft proposal',
};

export const CATEGORY_ORDER: NbaCategory[] = [
  'RISK',
  'COMMUNICATION',
  'MEETING',
  'QUALIFICATION',
  'INTERNAL',
  'CONTENT',
];

/** The engine's best action for a record, or `null` when nothing is recommended. */
export const topAction = (item: PriorityScore): NbaAction | null => item.actions[0] ?? null;

/* ---- Signal groups for the details drawer ---- */

export interface SignalGroup {
  title: string;
  keys: string[];
}

export const SIGNAL_GROUPS: SignalGroup[] = [
  {
    title: 'Stage & deal',
    keys: [
      'stage_name',
      'lead_status',
      'lead_priority',
      'days_in_stage',
      'deal_value',
      'expected_deal_size',
      'win_probability',
      'days_to_close',
      'competitor',
      'similar_deal_win_rate',
    ],
  },
  {
    title: 'Interactions',
    keys: [
      'days_since_last_interaction',
      'days_since_last_outbound',
      'days_since_last_customer_response',
      'awaiting_customer_response',
      'outbound_emails_30d',
      'inbound_emails_30d',
      'days_since_last_meeting',
      'completed_meeting_count',
      'upcoming_meeting_count',
      'demo_completed',
      'technical_workshop_completed',
      'pricing_discussed_recently',
    ],
  },
  {
    title: 'Follow-up',
    keys: ['open_task_count', 'overdue_task_count', 'has_follow_up_scheduled'],
  },
  {
    title: 'Stakeholders',
    keys: [
      'contact_count',
      'decision_maker_count',
      'technical_contact_count',
      'procurement_contact_count',
      'finance_contact_count',
      'engaged_contact_count_30d',
    ],
  },
  {
    title: 'History',
    keys: ['account_won_deals', 'account_lost_deals', 'account_is_customer', 'account_products'],
  },
  {
    title: 'Tracked through custom fields',
    keys: [
      'proposal_open_count',
      'proposal_opens_24h',
      'email_open_count',
      'email_click_count',
      'pricing_page_visits_7d',
      'budget_confirmed',
      'timeline_confirmed',
      'pain_points_confirmed',
      'procurement_verified',
      'license_utilization_pct',
      'days_to_subscription_end',
    ],
  },
];

export function formatSignal(value: string | number | boolean | null | undefined): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1);
  return value;
}

/* ---- Rules engine vocabulary ---- */

/** The layout/workflow condition operators the engine shares (`layouts/evaluate.py`). */
export const OPERATOR_LABEL: Record<string, string> = {
  equals: 'is',
  not_equals: 'is not',
  contains: 'contains',
  not_contains: 'does not contain',
  greater_than: 'is more than',
  less_than: 'is less than',
  is_empty: 'is unknown',
  is_not_empty: 'is known',
  in: 'is one of',
  not_in: 'is none of',
};

/** Operators that take no value. */
export const VALUELESS_OPERATORS = new Set(['is_empty', 'is_not_empty']);
/** Operators whose value is a list. */
export const LIST_OPERATORS = new Set(['in', 'not_in']);

export const APPLIES_TO_LABEL: Record<NbaRecordKind | 'BOTH', string> = {
  BOTH: 'Deals and leads',
  OPPORTUNITY: 'Deals',
  LEAD: 'Leads',
};

export function conditionValueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (Array.isArray(value)) return value.map(String).join(', ');
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  return String(value);
}

/* ---- Copilot drafts as plain text (Copy, task descriptions) ---- */

export function meetingAgendaText(content: CopilotMeetingContent): string {
  const lines = content.agenda.map(
    (item, index) => `${index + 1}. ${item.topic} — ${item.minutes} min\n   Objective: ${item.objective}`,
  );
  const attendees = content.attendee_roles.length > 0 ? `\n\nAttendees: ${content.attendee_roles.join(', ')}` : '';
  return `${content.description}\n\nAgenda\n${lines.join('\n')}${attendees}`.trim();
}

export function copilotToText(content: CopilotContent): string {
  switch (content.kind) {
    case 'EMAIL':
      return `Subject: ${content.subject}\n\n${content.body}`;
    case 'MESSAGE':
      return content.body;
    case 'MEETING_AGENDA':
      return `${content.title} (${content.duration_minutes} min)\n\n${meetingAgendaText(content)}`;
    case 'CALL_SCRIPT':
      return [
        `OPENING\n  ${content.opening}`,
        `QUESTIONS\n${content.questions.map((line) => `  - ${line}`).join('\n')}`,
        `TALKING POINTS\n${content.talking_points.map((line) => `  - ${line}`).join('\n')}`,
        `OBJECTIONS\n${content.objections.map((item) => `  - ${item.objection}\n    → ${item.response}`).join('\n')}`,
        `CLOSE\n  ${content.close}`,
      ].join('\n\n');
    case 'PROPOSAL':
      return [
        content.summary,
        ...content.sections.map((section) => `${section.title.toUpperCase()}\n${section.content}`),
        `NEXT STEPS\n${content.next_steps.map((step) => `  - ${step}`).join('\n')}`,
      ].join('\n\n');
  }
}

/** A stored Copilot draft, or `null` when the generation is not a usable one. */
export function copilotContentOf(generation: AiGeneration | null | undefined): CopilotContent | null {
  if (!generation || generation.status !== 'READY') return null;
  const content = generation.content as unknown as CopilotContent;
  return typeof content?.kind === 'string' ? content : null;
}

/** An ISO instant as a `datetime-local` value in the viewer's zone. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/* ---- Confidence (predictive actions and the fixture drawer) ---- */

export function confidenceTone(value: number): MeterTone {
  if (value >= 85) return 'positive';
  if (value >= 70) return 'accent';
  if (value >= 50) return 'caution';
  return 'negative';
}

export function confidenceLabel(value: number): string {
  if (value >= 85) return 'High confidence';
  if (value >= 70) return 'Good confidence';
  if (value >= 50) return 'Moderate confidence';
  return 'Low confidence';
}

/* ============================================================
   FIXTURE PRESENTATION

   Badge tones and Copy serialisers for the pre-Checkpoint-7
   fixture views (`NbaTable`, `NbaDetailsDrawer`), which read
   `features/ai/next-best-action` rather than the engine API.
   ============================================================ */

export const FIXTURE_PRIORITY_VARIANT: Record<NbaPriority, BadgeVariant> = {
  Critical: 'danger',
  High: 'warning',
  Medium: 'accent',
  Low: 'neutral',
};

export const STATUS_VARIANT: Record<NbaStatus, BadgeVariant> = {
  New: 'accent',
  Pending: 'warning',
  'In Progress': 'accent',
  Scheduled: 'accent',
  Completed: 'success',
  Dismissed: 'neutral',
};

export const SEVERITY_VARIANT: Record<RiskSeverity, BadgeVariant> = {
  Critical: 'danger',
  High: 'danger',
  Medium: 'warning',
  Low: 'neutral',
};

export const RISK_VARIANT: Record<DealRisk, BadgeVariant> = {
  Low: 'success',
  Medium: 'warning',
  High: 'danger',
  Critical: 'danger',
};

export const PROPOSAL_VARIANT: Record<ProposalStatus, BadgeVariant> = {
  Draft: 'neutral',
  Sent: 'accent',
  Viewed: 'accent',
  'Under Review': 'warning',
  'Revision Requested': 'warning',
  Approved: 'success',
};

export const SOW_VARIANT: Record<SowStatus, BadgeVariant> = {
  'Not Started': 'neutral',
  Drafting: 'accent',
  Shared: 'accent',
  'Legal Review': 'warning',
  Approved: 'success',
};

export function callScriptToText(sections: NbaDetail['callScript']): string {
  return sections
    .map((section) => `${section.label.toUpperCase()}\n${section.lines.map((line) => `  ${line}`).join('\n')}`)
    .join('\n\n');
}

export function agendaToText(items: NbaDetail['meetingAgenda']): string {
  const total = items.reduce((sum, item) => sum + item.minutes, 0);
  return `Suggested meeting agenda (${total} minutes)\n\n${items
    .map(
      (item, index) =>
        `${index + 1}. ${item.topic} — ${item.minutes} min\n   Objective: ${item.objective}\n   Participants: ${item.participants}`,
    )
    .join('\n')}`;
}

export function emailToText(email: NbaDetail['suggestedEmail']): string {
  return `Subject: ${email.subject}\n\n${email.body}`;
}
