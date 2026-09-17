import type { BadgeVariant } from '@/components/crm/shared/StatusBadge';
import type {
  AiGeneration,
  NextBestActionContent,
  PriorityScore,
} from '@/features/ai/ai-insights';

/* ============================================================
   NEXT BEST ACTION — VIEW HELPERS

   Presentation over what the priority API already returns. The
   ranking, levels, reasons and facts are all computed server-side
   (`ai_insights/prioritization.py`, `service.py`); nothing here
   scores, re-ranks or infers. The one thing this file decides is
   how the backend's own reason labels group into filter chips.
   ============================================================ */

export type RecordKind = PriorityScore['entity_type'];
export type PriorityLevel = PriorityScore['level'];

export const RECORD_ROUTE: Record<RecordKind, string> = {
  OPPORTUNITY: '/opportunities',
  LEAD: '/leads',
};

export const RECORD_NOUN: Record<RecordKind, string> = {
  OPPORTUNITY: 'Deal',
  LEAD: 'Lead',
};

export const LEVEL_LABEL: Record<PriorityLevel, string> = {
  HIGH: 'High priority',
  MEDIUM: 'Medium priority',
  LOW: 'Low priority',
};

/** Shared by the rules-based priority level and the model's urgency. */
export const LEVEL_VARIANT: Record<PriorityLevel, BadgeVariant> = {
  HIGH: 'danger',
  MEDIUM: 'warning',
  LOW: 'neutral',
};

export const recordHref = (item: Pick<PriorityScore, 'entity_type' | 'entity_id'>) =>
  `${RECORD_ROUTE[item.entity_type]}/${item.entity_id}`;

/* ---- Signals ----------------------------------------------------------- */

export type SignalFilter = 'CLOSING_SOON' | 'STALE' | 'NO_FOLLOW_UP' | 'OVERDUE' | 'AT_RISK';

export const SIGNAL_LABEL: Record<SignalFilter, string> = {
  CLOSING_SOON: 'Closing soon',
  STALE: 'Stale',
  NO_FOLLOW_UP: 'No follow-up',
  OVERDUE: 'Overdue tasks',
  AT_RISK: 'At risk',
};

/*
 * Reason labels are the scoring rules' own vocabulary, pinned by the backend's
 * prioritization tests. Grouped here only to filter on; a label the backend
 * stops emitting simply matches nothing.
 */
const CLOSING_SOON_REASONS = new Set(['Past close date', 'Closing soon']);
/** Gone quiet for the backend's staleness window — not merely "never worked yet". */
const STALE_REASONS = new Set(['Stalled', 'Not contacted recently']);
/** Record metadata the backend appends as a reason — shown as a fact, not a signal chip. */
const METADATA_REASONS = new Set(['Stage', 'Status']);
const ATTENTION_REASONS = new Set([
  ...CLOSING_SOON_REASONS,
  ...STALE_REASONS,
  'Never contacted',
  'No recorded activity',
  'Overdue task(s)',
  'No follow-up scheduled',
]);

/**
 * Whether a ranked record carries a signal.
 *
 * `atRiskIds` comes from the AI Insights digest (`GET /digest`), the product's
 * existing "deals at risk" rule — not a rule of this screen's own.
 */
export function hasSignal(
  item: PriorityScore,
  signal: SignalFilter,
  atRiskIds: ReadonlySet<string>,
): boolean {
  switch (signal) {
    case 'CLOSING_SOON':
      return item.reasons.some((reason) => CLOSING_SOON_REASONS.has(reason.label));
    case 'STALE':
      return item.reasons.some((reason) => STALE_REASONS.has(reason.label));
    case 'NO_FOLLOW_UP':
      return item.facts.open_task_count === 0;
    case 'OVERDUE':
      return item.facts.overdue_task_count > 0;
    case 'AT_RISK':
      return atRiskIds.has(item.entity_id);
  }
}

/** The reasons worth showing as chips, attention-worthy ones flagged. */
export function signalChips(item: PriorityScore): { label: string; detail: string; attention: boolean }[] {
  return item.reasons
    .filter((reason) => !METADATA_REASONS.has(reason.label))
    .map((reason) => ({ ...reason, attention: ATTENTION_REASONS.has(reason.label) }));
}

/** The backend's reason details as one sentence — the ranking's "why". */
export function rankingWhy(item: PriorityScore): string {
  const details = item.reasons
    .filter((reason) => !METADATA_REASONS.has(reason.label))
    .map((reason) => reason.detail);
  return details.length > 0 ? `${details.join('. ')}.` : 'No priority signals on this record right now.';
}

/** Stage for a deal, status for a lead — the backend's own wording. */
export function stageOrStatus(item: PriorityScore): string | null {
  const metadata = item.reasons.find((reason) => METADATA_REASONS.has(reason.label));
  return item.facts.stage_name ?? metadata?.detail ?? null;
}

/** Account for a deal, company for a lead. */
export function organizationOf(item: PriorityScore): string | null {
  return item.entity_type === 'OPPORTUNITY' ? item.facts.account_name : item.facts.company;
}

/* ---- Cached recommendation ------------------------------------------------ */

export interface Recommendation {
  generation: AiGeneration;
  content: NextBestActionContent;
}

/** A usable cached Next Best Action, or `null` when none was ever generated. */
export function recommendationOf(generation: AiGeneration | null | undefined): Recommendation | null {
  if (!generation || generation.status !== 'READY') return null;
  const content = generation.content as unknown as NextBestActionContent;
  if (typeof content?.action !== 'string' || !content.action) return null;
  return { generation, content };
}

/* ---- Dates -------------------------------------------------------------- */

const DAY_MS = 86_400_000;

/** A `YYYY-MM-DD` date as local midnight — `new Date(iso)` would read it as UTC. */
function parseDateOnly(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

function shortDate(date: Date): string {
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;

export type Tone = 'neutral' | 'warning' | 'danger';

export interface Described {
  text: string;
  tone: Tone;
}

/**
 * Last activity, counted in whole days the way the backend counts staleness
 * (`(now - last).days`), so "20 days ago" agrees with a "Stalled" reason.
 */
export function describeLastActivity(iso: string | null, now: Date): Described {
  if (!iso) return { text: 'No activity logged', tone: 'warning' };
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return { text: '—', tone: 'neutral' };
  const days = Math.floor((now.getTime() - then.getTime()) / DAY_MS);
  // A planned activity's due date counts as its activity date server-side.
  if (days < 0) return { text: `Planned ${shortDate(then)}`, tone: 'neutral' };
  if (days === 0) return { text: 'Today', tone: 'neutral' };
  if (days === 1) return { text: 'Yesterday', tone: 'neutral' };
  return { text: `${days} days ago`, tone: 'neutral' };
}

export function describeCloseDate(iso: string | null, now: Date): Described | null {
  if (!iso) return null;
  const date = parseDateOnly(iso);
  if (!date) return { text: iso, tone: 'neutral' };
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round((date.getTime() - today.getTime()) / DAY_MS);
  if (days < 0) return { text: `${shortDate(date)} · ${plural(-days, 'day')} past`, tone: 'danger' };
  if (days === 0) return { text: `${shortDate(date)} · today`, tone: 'warning' };
  return { text: `${shortDate(date)} · in ${plural(days, 'day')}`, tone: days <= 7 ? 'warning' : 'neutral' };
}

export function describeFollowUp(item: PriorityScore): Described {
  const { open_task_count: open, overdue_task_count: overdue } = item.facts;
  if (overdue > 0) return { text: `${overdue} overdue · ${plural(open, 'open task')}`, tone: 'danger' };
  if (open > 0) return { text: plural(open, 'open task'), tone: 'neutral' };
  return { text: 'No follow-up scheduled', tone: 'warning' };
}

export const TONE_TEXT: Record<Tone, string> = {
  neutral: 'txt',
  warning: 'text-amber-600 dark:text-amber-400',
  danger: 'text-rose-600 dark:text-rose-400',
};
