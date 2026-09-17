'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, Sparkles, Zap } from 'lucide-react';

import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import { useAiStatus } from '@/features/ai/useAiStatus';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  explainLeadPriority,
  explainOpportunityPriority,
  priorityLeads,
  priorityOpportunities,
  type PriorityScore,
} from '@/features/ai/ai-insights';

/* ============================================================
   NEXT BEST ACTION

   The ranking itself is rules over real CRM fields — deal value,
   close date, win probability, days since activity, overdue tasks
   — never a model's guess (see `ai_insights/prioritization.py`).
   It renders with no AI connection required. "Explain" calls the
   model only to narrate the reasons already computed here; it
   never invents a new one.
   ============================================================ */

const LEVEL_CLASS: Record<PriorityScore['level'], string> = {
  HIGH: 'border-rose-500/30 bg-rose-500/10 text-rose-600',
  MEDIUM: 'border-amber-500/30 bg-amber-500/10 text-amber-600',
  LOW: 'border-[var(--border)] bg-[var(--surface-2)] txt-muted',
};

function PriorityRow({
  score,
  label,
  href,
  onExplain,
}: {
  score: PriorityScore;
  label: string;
  href: string;
  onExplain: () => Promise<void>;
}) {
  const [explaining, setExplaining] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function explain() {
    setExplaining(true);
    setError(null);
    try {
      await onExplain();
      setExplanation('shown');
    } catch (caught) {
      setError(describeApiError(caught, 'Could not explain this priority.'));
    } finally {
      setExplaining(false);
    }
  }

  return (
    <div className="bd border-b py-3 last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href={href} className="txt truncate text-[13px] font-semibold hover:underline">
            {label}
          </Link>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
            {score.reasons.slice(0, 3).map((reason) => (
              <span key={reason.label} className="txt-muted text-[11.5px]">
                {reason.label}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${LEVEL_CLASS[score.level]}`}
          >
            {score.level} · {score.score}
          </span>
          <button
            type="button"
            onClick={() => void explain()}
            disabled={explaining}
            className="ctl bd rounded-lg border px-2.5 py-1 text-[11.5px] font-medium transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {explaining ? (
              <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
            ) : (
              'Explain'
            )}
          </button>
        </div>
      </div>
      {error && <p className="mt-1.5 text-[11.5px] text-rose-600">{error}</p>}
      {explanation && (
        <p className="txt-muted mt-1.5 text-[12px]">
          Explanation saved to this record&apos;s AI history — open it to read the reasoning.
        </p>
      )}
    </div>
  );
}

function PriorityQueue({
  title,
  items,
  hrefBase,
  labelOf,
  onExplain,
}: {
  title: string;
  items: PriorityScore[];
  hrefBase: string;
  labelOf: (score: PriorityScore) => string;
  onExplain: (score: PriorityScore) => Promise<void>;
}) {
  return (
    <section className="surface bd rounded-2xl border p-5">
      <h2 className="txt font-display text-[14px] font-bold">
        {title} <span className="txt-faint font-normal">({items.length})</span>
      </h2>
      {items.length === 0 ? (
        <p className="txt-muted mt-2 text-[12.5px]">Nothing open to prioritize right now.</p>
      ) : (
        <div className="mt-1">
          {items.map((score) => (
            <PriorityRow
              key={score.entity_id}
              score={score}
              label={labelOf(score)}
              href={`${hrefBase}/${score.entity_id}`}
              onExplain={() => onExplain(score)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default function NextBestActionPage() {
  const { status, error: statusError } = useAiStatus();
  const [opportunities, setOpportunities] = useState<PriorityScore[]>([]);
  const [leads, setLeads] = useState<PriorityScore[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const loading = !loaded && loadError === null;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [opps, ldsResult] = await Promise.all([priorityOpportunities(), priorityLeads()]);
        if (cancelled) return;
        setOpportunities(opps.items);
        setLeads(ldsResult.items);
        setLoaded(true);
      } catch (caught) {
        if (!cancelled) setLoadError(describeApiError(caught, 'Could not load the priority queue.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
          <Zap className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Next Best Action</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            Which open deals and leads to work on next, ranked from your own CRM data.
          </p>
        </div>
      </div>

      <AiConnectionNotice
        status={status}
        error={statusError}
        hideWhenReady
        consequence="The ranking below still works — it's computed from CRM fields, not the model. AI connection is only needed to explain a score in plain language, or to generate a full next-best-action recommendation from a record page."
      />

      {loading && (
        <div role="status" aria-busy="true" className="txt-muted flex items-center gap-2 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> Loading the priority
          queue…
        </div>
      )}

      {loadError && (
        <p role="alert" className="flex items-center gap-2 text-[13px] text-rose-600">
          <AlertTriangle className="h-4 w-4" aria-hidden="true" /> {loadError}
        </p>
      )}

      {!loading && !loadError && (
        <div className="grid gap-4 sm:grid-cols-2">
          <PriorityQueue
            title="Deals"
            items={opportunities}
            hrefBase="/opportunities"
            labelOf={(score) => score.entity_label}
            onExplain={(score) => explainOpportunityPriority(score.entity_id).then(() => undefined)}
          />
          <PriorityQueue
            title="Leads"
            items={leads}
            hrefBase="/leads"
            labelOf={(score) => score.entity_label}
            onExplain={(score) => explainLeadPriority(score.entity_id).then(() => undefined)}
          />
        </div>
      )}

      <p className="txt-faint flex items-center gap-1.5 text-[11.5px]">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" /> Ranked by deal size, close date, win
        probability, recent activity and overdue tasks — see the reasons on each row.
      </p>
    </div>
  );
}
