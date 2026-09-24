'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  Activity,
  ArrowUpRight,
  BrainCircuit,
  ClipboardList,
  Gauge,
  ListChecks,
  Loader2,
  RefreshCw,
  Sparkles,
} from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import AiFeedbackButtons from '@/components/crm/ai/AiFeedbackButtons';
import { formatMoney } from '@/features/crm/dashboard/presenters';
import { formatCheckedAt, type AiStatus } from '@/features/ai/status';
import type { AiGeneration, PriorityScore } from '@/features/ai/ai-insights';
import { cn } from '@/lib/utils';
import { humanize } from '@/components/crm/shared/statusVariants';
import NbaEngineActions, { type NbaEngineHandlers } from './NbaEngineActions';
import { SIGNAL_GROUPS, formatSignal } from './nba-helpers';
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
  recommendationOf,
  recordHref,
  stageOrStatus,
  type Described,
} from './nba-view';

/* ============================================================
   NBA EXPLAIN DRAWER

   Three things, kept visibly apart so nobody mistakes one for
   another:

   1. The AI recommendation — the record's stored Next Best Action
      (`/next-best-action`), or a Generate button.
   2. Why it is ranked here — the rule-based reasons, computed from
      CRM fields with no model involved.
   3. The AI explanation — the model narrating those same reasons
      (`/priority/.../explain`). It is asked when "Explain" is
      pressed, never on page load, and cannot add a reason of its
      own: the backend sends it only the computed ones.

   With AI unavailable, (2) and the record facts still render and
   the existing AI-not-connected notice explains the rest.
   ============================================================ */

export type ExplanationState =
  | { status: 'loading' }
  | { status: 'ready'; generation: AiGeneration }
  | { status: 'error'; message: string };

function Section({
  icon: Icon,
  title,
  note,
  aside,
  children,
}: {
  icon: typeof Sparkles;
  title: string;
  note?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="surface bd rounded-2xl border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="txt font-display flex items-center gap-2 text-[13.5px] font-bold">
            <Icon className="h-4 w-4" style={{ color: 'var(--accent)' }} aria-hidden="true" />
            {title}
          </h3>
          {note && <p className="txt-faint mt-0.5 text-[11.5px]">{note}</p>}
        </div>
        {aside}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string | Described | null }) {
  const described = typeof value === 'object' && value !== null ? value : null;
  const text = described ? described.text : (value as string | null);
  return (
    <div className="min-w-0">
      <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">{label}</dt>
      <dd className={cn('mt-0.5 break-words text-[12.5px] font-medium', described ? TONE_TEXT[described.tone] : 'txt')}>
        {text || '—'}
      </dd>
    </div>
  );
}

const smallButton =
  'ctl inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60';

export default function NbaExplainDrawer({
  item,
  rank,
  now,
  explanation,
  onExplain,
  aiStatus,
  aiError,
  aiReady,
  canUseAi,
  generating,
  generateError,
  onGenerate,
  onAction,
  onClose,
  engine,
  signalLabels,
}: {
  engine: NbaEngineHandlers;
  /** Signal key -> label, from the engine catalog; keys are humanized until it loads. */
  signalLabels: ReadonlyMap<string, string>;
  item: PriorityScore | null;
  rank: number | null;
  /** When the queue was loaded — relative dates are read against it. */
  now: Date;
  explanation: ExplanationState | null;
  onExplain: () => void;
  aiStatus: AiStatus | null;
  aiError: string | null;
  aiReady: boolean;
  /** `ai_insights.CREATE` — needed to ask the model for anything. */
  canUseAi: boolean;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
  onAction: (kind: NbaActionKind, item: PriorityScore) => void;
  onClose: () => void;
}) {
  if (!item) return null;

  const recommendation = recommendationOf(item.latest_recommendation);
  const organization = organizationOf(item);
  const stage = stageOrStatus(item);
  const mayAsk = aiReady && canUseAi;
  const facts = item.facts;
  const isDeal = item.entity_type === 'OPPORTUNITY';
  const signalGroups = SIGNAL_GROUPS.map((group) => ({
    title: group.title,
    rows: group.keys.flatMap((key) => {
      const value = formatSignal(item.signals[key]);
      return value === null ? [] : [{ key, label: signalLabels.get(key) ?? humanize(key), value }];
    }),
  })).filter((group) => group.rows.length > 0);

  const generateButton = mayAsk ? (
    <button type="button" onClick={onGenerate} disabled={generating} className={smallButton}>
      {generating ? (
        <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
      ) : recommendation ? (
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {generating ? 'Generating…' : recommendation ? 'Refresh' : 'Generate'}
    </button>
  ) : null;

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title={item.entity_label}
      subtitle={[RECORD_NOUN[item.entity_type], organization, stage].filter(Boolean).join(' · ')}
      width="max-w-2xl"
      footer={
        <>
          <Link
            href={recordHref(item)}
            className="ctl inline-flex items-center gap-1.5 px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
          >
            Open record <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
          <NbaTakeActionMenu item={item} onAction={onAction} placement="up" />
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={LEVEL_LABEL[item.level]} variant={LEVEL_VARIANT[item.level]} />
          <span className="txt-muted text-[12px] font-semibold">Priority score {item.score}/100</span>
          {rank !== null && <span className="txt-faint text-[12px]">· #{rank} in your queue</span>}
        </div>

        {(!aiReady || aiError) && (
          <AiConnectionNotice
            status={aiStatus}
            error={aiError}
            hideWhenReady
            compact
            consequence="The ranking and record details below still work — they come from CRM fields. Generating a recommendation or an explanation needs the AI connection."
          />
        )}

        {/* 0 — the engine's actions (rules + similar-deal history) */}
        <Section
          icon={ListChecks}
          title="Next best actions"
          note="From the rules engine and similar won deals — no AI involved."
        >
          <NbaEngineActions item={item} handlers={engine} detailed />
        </Section>

        {/* 1 — the stored recommendation */}
        {recommendation ? (
          <NbaRecommendationBlock
            recommendation={recommendation}
            headerAside={<AiFeedbackButtons key={recommendation.generation.id} generation={recommendation.generation} />}
            footer={generateButton}
          />
        ) : (
          <NbaNoRecommendation
            note={
              mayAsk
                ? 'Generate one from this record’s CRM context — it is saved to the record’s AI history.'
                : 'None has been generated for this record.'
            }
          >
            {generateButton}
          </NbaNoRecommendation>
        )}
        {generateError && (
          <p role="alert" className="text-[12px] text-rose-600">
            {generateError}
          </p>
        )}

        {/* 2 — rule-based reasons */}
        <Section icon={Gauge} title="Why it’s ranked here" note="Computed from CRM fields — no AI involved.">
          {item.reasons.length === 0 ? (
            <p className="txt-muted text-[12.5px]">No priority signals on this record right now.</p>
          ) : (
            <ul className="space-y-2">
              {item.reasons.map((reason) => (
                <li key={`${reason.label}-${reason.detail}`} className="flex gap-2.5 text-[12.5px]">
                  <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: 'var(--accent)' }} />
                  <span>
                    <span className="txt font-semibold">{reason.label}</span>
                    <span className="txt-muted"> — {reason.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* 2b — the signal snapshot the engine read */}
        {signalGroups.length > 0 && (
          <Section icon={Activity} title="Signals" note="The CRM signals the engine evaluated for this record.">
            <div className="space-y-3">
              {signalGroups.map((group) => (
                <div key={group.title}>
                  <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">{group.title}</p>
                  <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
                    {group.rows.map((row) => (
                      <div key={row.key} className="min-w-0">
                        <dt className="txt-muted truncate text-[11.5px]">{row.label}</dt>
                        <dd className="txt text-[12.5px] font-semibold">{row.value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* 3 — the model's narration of those reasons */}
        <Section
          icon={BrainCircuit}
          title="AI explanation"
          note="A plain-language reading of the reasons above."
          aside={
            mayAsk && explanation?.status !== 'loading' ? (
              <button type="button" onClick={onExplain} className={smallButton}>
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                {explanation?.status === 'ready' ? 'Regenerate' : explanation ? 'Try again' : 'Explain'}
              </button>
            ) : null
          }
        >
          {!mayAsk && !explanation ? (
            <p className="txt-muted text-[12.5px]">
              {canUseAi
                ? 'Available once the AI connection is ready.'
                : 'You do not have permission to request AI explanations.'}
            </p>
          ) : explanation?.status === 'loading' ? (
            <p role="status" aria-busy="true" className="txt-muted flex items-center gap-2 text-[12.5px]">
              <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> Asking the model to
              explain this ranking…
            </p>
          ) : explanation?.status === 'error' ? (
            <p role="alert" className="text-[12.5px] text-rose-600">
              {explanation.message}
            </p>
          ) : explanation?.status === 'ready' ? (
            <div>
              <p className="txt text-[13px] leading-relaxed">
                {String((explanation.generation.content as { explanation?: unknown }).explanation ?? '')}
              </p>
              <div className="mt-2 flex items-center justify-between gap-2">
                <p className="txt-faint text-[11px]">
                  Generated {formatCheckedAt(explanation.generation.created_at) || 'just now'}
                  {explanation.generation.model ? ` · ${explanation.generation.model}` : ''}
                </p>
                <AiFeedbackButtons key={explanation.generation.id} generation={explanation.generation} />
              </div>
            </div>
          ) : (
            <p className="txt-muted text-[12.5px]">Press Explain to ask the model.</p>
          )}
        </Section>

        {/* Record facts */}
        <Section icon={ClipboardList} title="Record details">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            {isDeal ? (
              <>
                <Fact label="Account" value={facts.account_name ?? (facts.account_id ? 'Not visible to you' : null)} />
                <Fact label="Stage" value={stage} />
                <Fact
                  label="Deal value"
                  value={facts.deal_value !== null ? formatMoney(facts.deal_value) : null}
                />
                <Fact
                  label="Win probability"
                  value={facts.win_probability !== null ? `${facts.win_probability}%` : null}
                />
                <Fact label="Expected close" value={describeCloseDate(facts.expected_close_date, now)} />
              </>
            ) : (
              <>
                <Fact label="Company" value={facts.company} />
                <Fact label="Status" value={stage} />
                <Fact
                  label="Expected deal size"
                  value={facts.expected_deal_size !== null ? formatMoney(facts.expected_deal_size) : null}
                />
                <Fact label="Email" value={facts.email} />
                <Fact label="Phone" value={facts.phone} />
              </>
            )}
            <Fact label="Last activity" value={describeLastActivity(facts.last_activity_at, now)} />
            <Fact label="Follow-up" value={describeFollowUp(item)} />
          </dl>
        </Section>
      </div>
    </SlideDrawer>
  );
}
