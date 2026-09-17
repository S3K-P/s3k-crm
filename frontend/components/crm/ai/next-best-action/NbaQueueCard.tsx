'use client';

import Link from 'next/link';
import { ArrowUpRight, Briefcase, Loader2, Sparkles, UserRound } from 'lucide-react';

import StatusBadge from '@/components/crm/shared/StatusBadge';
import { formatMoney } from '@/features/crm/dashboard/presenters';
import type { PriorityScore } from '@/features/ai/ai-insights';
import { cn } from '@/lib/utils';
import { NbaNoRecommendation, NbaRecommendationBlock } from './NbaRecommendation';
import NbaTakeActionMenu, { type NbaActionKind } from './NbaTakeActionMenu';
import {
  LEVEL_LABEL,
  LEVEL_VARIANT,
  RECORD_NOUN,
  TONE_TEXT,
  describeCloseDate,
  describeFollowUp,
  describeLastActivity,
  organizationOf,
  rankingWhy,
  recommendationOf,
  recordHref,
  signalChips,
  stageOrStatus,
  type Described,
} from './nba-view';

/* ============================================================
   NBA QUEUE CARD

   One ranked record: who it is, what to do (the stored AI
   recommendation, or its absence), why it ranks here, the CRM
   facts behind that, and the three calls to action.

   Desktop reads left to right — identity, recommendation, facts.
   Tablet folds the facts under the recommendation. Phones keep
   priority, recommendation, reason and actions, and leave the
   fact grid to the Explain drawer.
   ============================================================ */

function FactRow({ label, value }: { label: string; value: string | Described | null }) {
  const described = typeof value === 'object' && value !== null ? value : null;
  const text = described ? described.text : (value as string | null);
  return (
    <div className="min-w-0">
      <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">{label}</dt>
      <dd
        className={cn(
          'mt-0.5 truncate text-[12.5px] font-semibold',
          described ? TONE_TEXT[described.tone] : 'txt',
        )}
        title={text ?? undefined}
      >
        {text || '—'}
      </dd>
    </div>
  );
}

export default function NbaQueueCard({
  item,
  rank,
  now,
  canGenerate,
  generating,
  generateError,
  onGenerate,
  onExplain,
  onAction,
}: {
  item: PriorityScore;
  rank: number;
  now: Date;
  /** AI is ready and the caller holds `ai_insights.CREATE`. */
  canGenerate: boolean;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
  onExplain: () => void;
  onAction: (kind: NbaActionKind, item: PriorityScore) => void;
}) {
  const recommendation = recommendationOf(item.latest_recommendation);
  const organization = organizationOf(item);
  const stage = stageOrStatus(item);
  const chips = signalChips(item);
  const isDeal = item.entity_type === 'OPPORTUNITY';
  const KindIcon = isDeal ? Briefcase : UserRound;
  const { facts } = item;

  const value = isDeal
    ? facts.deal_value !== null
      ? formatMoney(facts.deal_value, facts.currency)
      : null
    : facts.expected_deal_size !== null
      ? formatMoney(facts.expected_deal_size, null)
      : null;

  return (
    <article
      className="surface bd rounded-2xl border p-4 transition-shadow hover:shadow-[0_12px_28px_-18px_rgba(50,30,90,0.35)] sm:p-5"
      aria-labelledby={`nba-${item.entity_id}`}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] xl:grid-cols-[minmax(0,4fr)_minmax(0,6fr)_minmax(0,2.6fr)]">
        {/* Identity & signals */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display txt-faint text-[12px] font-bold tabular-nums">#{rank}</span>
            <StatusBadge label={LEVEL_LABEL[item.level]} variant={LEVEL_VARIANT[item.level]} />
            <span className="txt-faint text-[11.5px] font-semibold tabular-nums" title="Rule-based priority score">
              {item.score}/100
            </span>
          </div>
          <Link
            id={`nba-${item.entity_id}`}
            href={recordHref(item)}
            className="txt font-display mt-1.5 block truncate text-[15.5px] font-bold hover:underline"
          >
            {item.entity_label}
          </Link>
          <p className="txt-muted mt-0.5 flex min-w-0 items-center gap-1.5 text-[12px]">
            <KindIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">
              {[RECORD_NOUN[item.entity_type], organization, stage].filter(Boolean).join(' · ')}
            </span>
          </p>
          {chips.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="CRM signals">
              {chips.map((chip) => (
                <li
                  key={`${chip.label}-${chip.detail}`}
                  title={chip.detail}
                  className={cn(
                    'rounded-md border px-2 py-0.5 text-[11px] font-semibold',
                    chip.attention
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                      : 'bd txt-muted bg-[var(--surface-2)]',
                  )}
                >
                  {chip.label}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Recommendation & reason */}
        <div className="min-w-0 space-y-2">
          {recommendation ? (
            <NbaRecommendationBlock recommendation={recommendation} compact />
          ) : (
            <NbaNoRecommendation>
              {canGenerate && (
                <button
                  type="button"
                  onClick={onGenerate}
                  disabled={generating}
                  className="ctl inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {generating ? (
                    <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {generating ? 'Generating…' : 'Generate'}
                </button>
              )}
            </NbaNoRecommendation>
          )}
          {generateError && (
            <p role="alert" className="text-[12px] text-rose-600">
              {generateError}
            </p>
          )}
          <p className="txt-muted text-[12px] leading-relaxed">
            <span className="txt font-semibold">Ranked because: </span>
            {rankingWhy(item)}
          </p>
        </div>

        {/* Facts — folded under on tablet, left to the drawer on phones */}
        <dl className="bd hidden grid-cols-2 gap-x-4 gap-y-2.5 border-t pt-3 sm:grid lg:col-span-2 lg:grid-cols-4 xl:col-span-1 xl:grid-cols-1 xl:border-l xl:border-t-0 xl:pl-4 xl:pt-0">
          <FactRow label={isDeal ? 'Deal value' : 'Expected size'} value={value} />
          {isDeal && <FactRow label="Expected close" value={describeCloseDate(facts.expected_close_date, now)} />}
          <FactRow label="Last activity" value={describeLastActivity(facts.last_activity_at, now)} />
          <FactRow label="Follow-up" value={describeFollowUp(item)} />
        </dl>
      </div>

      <div className="bd mt-4 flex flex-wrap items-center justify-end gap-2 border-t pt-3">
        <button
          type="button"
          onClick={onExplain}
          className="ctl inline-flex items-center gap-1.5 px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
        >
          <Sparkles className="h-3.5 w-3.5" style={{ color: 'var(--accent)' }} aria-hidden="true" />
          Explain
        </button>
        <Link
          href={recordHref(item)}
          className="txt-muted inline-flex items-center gap-1 rounded-lg px-3 py-2 text-[12.5px] font-semibold transition hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
        >
          Open record <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
        <NbaTakeActionMenu item={item} onAction={onAction} />
      </div>
    </article>
  );
}
