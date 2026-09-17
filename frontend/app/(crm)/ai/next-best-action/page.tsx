'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw, SearchX, Sparkles, Zap } from 'lucide-react';

import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import ComposeEmailDrawer from '@/components/crm/emails/ComposeEmailDrawer';
import { ListError } from '@/components/crm/shared/ListStates';
import NbaAiStatusPill from '@/components/crm/ai/next-best-action/NbaAiStatusPill';
import { NbaMeetingDrawer, NbaTaskDrawer } from '@/components/crm/ai/next-best-action/NbaActionDrawers';
import NbaExplainDrawer, { type ExplanationState } from '@/components/crm/ai/next-best-action/NbaExplainDrawer';
import NbaKpiStrip, { type NbaKpiShortcut } from '@/components/crm/ai/next-best-action/NbaKpiStrip';
import NbaQueueCard from '@/components/crm/ai/next-best-action/NbaQueueCard';
import NbaQueueToolbar, {
  EMPTY_FILTERS,
  type QueueFilters,
  type QueueScope,
} from '@/components/crm/ai/next-best-action/NbaQueueToolbar';
import type { NbaActionKind } from '@/components/crm/ai/next-best-action/NbaTakeActionMenu';
import {
  hasSignal,
  organizationOf,
  recommendationOf,
  type SignalFilter,
} from '@/components/crm/ai/next-best-action/nba-view';
import { usePermissions } from '@/context/AuthContext';
import { getContact } from '@/features/crm/contacts';
import { getOpportunity } from '@/features/crm/opportunities';
import { availabilityOf } from '@/features/ai/status';
import { useAiStatus } from '@/features/ai/useAiStatus';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  explainLeadPriority,
  explainOpportunityPriority,
  generateLeadNextBestAction,
  generateOpportunityNextBestAction,
  getInsightsDigest,
  priorityLeads,
  priorityOpportunities,
  type AiGeneration,
  type PriorityScore,
} from '@/features/ai/ai-insights';

/* ============================================================
   NEXT BEST ACTION

   "What should I work on right now?" — one ranked queue of the
   caller's open deals and leads.

   Where each part comes from, and nothing else:

   - Rank, priority level, score, reasons and record facts:
     `GET /priority/{opportunities,leads}` — rules over real CRM
     fields (`ai_insights/prioritization.py`), no model call. The
     queue renders with AI disconnected.
   - "Recommended action": the record's stored Next Best Action,
     returned with the queue. Generating a new one is an explicit
     button press (`POST .../next-best-action`), never a page load.
   - "Deals at risk": the AI Insights digest's own rule (`/digest`).
   - "Explain": `POST /priority/.../explain` — the model narrating
     the reasons already computed, and nothing it invented.

   Deals and leads are merged by that same 0–100 score; filters
   only narrow the list, never re-rank it.
   ============================================================ */

/** The API's own ceiling for one ranked list. */
const QUEUE_LIMIT = 100;
const PAGE_SIZE = 12;

const NO_IDS: ReadonlySet<string> = new Set();
/** Only ever read while a drawer is closed (no queue loaded means no record to open). */
const EPOCH = new Date(0);

interface QueueData {
  deals: PriorityScore[];
  leads: PriorityScore[];
  /** Relative dates ("3 days ago") are read against the load time, not render time. */
  loadedAt: Date;
}

type DigestState = ReadonlySet<string> | 'loading' | 'unavailable';

type ActionState =
  | { kind: 'task' | 'meeting'; item: PriorityScore }
  | { kind: 'email'; item: PriorityScore; to: string | null };

const SHORTCUT_FILTERS: Record<NbaKpiShortcut, QueueFilters> = {
  ALL: EMPTY_FILTERS,
  HIGH: { ...EMPTY_FILTERS, level: 'HIGH' },
  AT_RISK: { ...EMPTY_FILTERS, scope: 'OPPORTUNITY', signals: ['AT_RISK'] },
  LEADS_NO_FOLLOW_UP: { ...EMPTY_FILTERS, scope: 'LEAD', signals: ['NO_FOLLOW_UP'] },
};

const ALL_SIGNALS: SignalFilter[] = ['CLOSING_SOON', 'STALE', 'NO_FOLLOW_UP', 'OVERDUE', 'AT_RISK'];

function sameFilters(a: QueueFilters, b: QueueFilters): boolean {
  return (
    a.scope === b.scope &&
    a.search === b.search &&
    a.level === b.level &&
    a.signals.length === b.signals.length &&
    a.signals.every((signal) => b.signals.includes(signal))
  );
}

function matchesSearch(item: PriorityScore, term: string): boolean {
  if (!term) return true;
  const haystack = [
    item.entity_label,
    organizationOf(item),
    item.facts.stage_name,
    recommendationOf(item.latest_recommendation)?.content.action,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return haystack.includes(term);
}

function withRecommendation(items: PriorityScore[], id: string, generation: AiGeneration): PriorityScore[] {
  return items.map((item) => (item.entity_id === id ? { ...item, latest_recommendation: generation } : item));
}

function QueueSkeleton() {
  return (
    <div className="space-y-5" aria-hidden="true">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="surface bd h-[104px] rounded-2xl border motion-safe:animate-pulse" />
        ))}
      </div>
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="surface bd rounded-2xl border p-5">
          <div className="h-3 w-32 rounded motion-safe:animate-pulse" style={{ background: 'var(--border)' }} />
          <div className="mt-3 h-4 w-64 max-w-full rounded motion-safe:animate-pulse" style={{ background: 'var(--border)' }} />
          <div className="mt-4 h-16 rounded-xl motion-safe:animate-pulse" style={{ background: 'var(--surface-2)' }} />
        </div>
      ))}
    </div>
  );
}

export default function NextBestActionPage() {
  const { status, error: statusError, loading: statusLoading } = useAiStatus();
  const { can } = usePermissions();
  const aiReady = status !== null && availabilityOf(status.state) === 'ready';
  const canUseAi = can('ai_insights', 'CREATE');

  /* ---- Data ---- */
  const [data, setData] = useState<QueueData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [digest, setDigest] = useState<DigestState>('loading');
  const [reloadToken, setReloadToken] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [deals, leads] = await Promise.all([
          priorityOpportunities(QUEUE_LIMIT),
          priorityLeads(QUEUE_LIMIT),
        ]);
        if (cancelled) return;
        setData({ deals: deals.items, leads: leads.items, loadedAt: new Date() });
        setLoadError(null);
      } catch (caught) {
        if (!cancelled) setLoadError(describeApiError(caught, 'Could not load the priority queue.'));
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // Loaded on its own: the queue must not wait on, or fail with, the digest.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getInsightsDigest();
        if (!cancelled) setDigest(new Set(result.deals_at_risk.map((insight) => insight.entity_id)));
      } catch {
        if (!cancelled) setDigest('unavailable');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const reload = useCallback(() => {
    setRefreshing(true);
    setReloadToken((n) => n + 1);
  }, []);

  /* ---- Derived queue ---- */
  const queue = useMemo(
    () => (data ? [...data.deals, ...data.leads].sort((a, b) => b.score - a.score) : []),
    [data],
  );
  const rankOf = useMemo(() => new Map(queue.map((item, index) => [item.entity_id, index + 1])), [queue]);
  const atRiskIds = typeof digest === 'string' ? NO_IDS : digest;

  const [filters, setFilters] = useState<QueueFilters>(EMPTY_FILTERS);
  const [visible, setVisible] = useState(PAGE_SIZE);

  const changeFilters = (next: QueueFilters) => {
    setFilters(next);
    setVisible(PAGE_SIZE);
  };

  const inScope = useMemo(
    () => queue.filter((item) => filters.scope === 'ALL' || item.entity_type === filters.scope),
    [queue, filters.scope],
  );

  const availableSignals = ALL_SIGNALS.filter(
    (signal) => signal !== 'AT_RISK' || (typeof digest !== 'string' && filters.scope !== 'LEAD'),
  );

  const signalCounts = useMemo(() => {
    const counts = {} as Record<SignalFilter, number>;
    for (const signal of ALL_SIGNALS) {
      counts[signal] = inScope.filter((item) => hasSignal(item, signal, atRiskIds)).length;
    }
    return counts;
  }, [inScope, atRiskIds]);

  const filtered = useMemo(() => {
    const term = filters.search.trim().toLowerCase();
    return inScope.filter(
      (item) =>
        (!filters.level || item.level === filters.level) &&
        filters.signals.every((signal) => hasSignal(item, signal, atRiskIds)) &&
        matchesSearch(item, term),
    );
  }, [inScope, filters.level, filters.signals, filters.search, atRiskIds]);

  const scopeCounts: Record<QueueScope, number> = {
    ALL: queue.length,
    OPPORTUNITY: data?.deals.length ?? 0,
    LEAD: data?.leads.length ?? 0,
  };

  const kpis = {
    queued: queue.length,
    deals: data?.deals.length ?? 0,
    leads: data?.leads.length ?? 0,
    high: queue.filter((item) => item.level === 'HIGH').length,
    atRisk: typeof digest === 'string' ? digest : digest.size,
    leadsWithoutFollowUp: (data?.leads ?? []).filter((item) => hasSignal(item, 'NO_FOLLOW_UP', NO_IDS)).length,
  };
  const activeShortcut =
    (Object.keys(SHORTCUT_FILTERS) as NbaKpiShortcut[]).find((key) => sameFilters(filters, SHORTCUT_FILTERS[key])) ??
    null;

  /* ---- Generate a recommendation (explicit, one record) ---- */
  const [generating, setGenerating] = useState<ReadonlySet<string>>(NO_IDS);
  const [generateErrors, setGenerateErrors] = useState<Record<string, string>>({});

  const generate = async (item: PriorityScore) => {
    const id = item.entity_id;
    if (generating.has(id)) return;
    setGenerating((previous) => new Set(previous).add(id));
    setGenerateErrors((previous) => {
      const next = { ...previous };
      delete next[id];
      return next;
    });
    try {
      const generation =
        item.entity_type === 'OPPORTUNITY'
          ? await generateOpportunityNextBestAction(id)
          : await generateLeadNextBestAction(id);
      setData((previous) =>
        previous
          ? {
              ...previous,
              deals: withRecommendation(previous.deals, id, generation),
              leads: withRecommendation(previous.leads, id, generation),
            }
          : previous,
      );
    } catch (caught) {
      setGenerateErrors((previous) => ({
        ...previous,
        [id]: describeApiError(caught, 'Could not generate a recommendation.'),
      }));
    } finally {
      setGenerating((previous) => {
        const next = new Set(previous);
        next.delete(id);
        return next;
      });
    }
  };

  /* ---- Explain ---- */
  const [explainId, setExplainId] = useState<string | null>(null);
  const [explanations, setExplanations] = useState<Record<string, ExplanationState>>({});
  const explainItem = explainId ? (queue.find((item) => item.entity_id === explainId) ?? null) : null;

  const requestExplanation = async (item: PriorityScore) => {
    const id = item.entity_id;
    setExplanations((previous) => ({ ...previous, [id]: { status: 'loading' } }));
    try {
      const generation =
        item.entity_type === 'OPPORTUNITY'
          ? await explainOpportunityPriority(id)
          : await explainLeadPriority(id);
      setExplanations((previous) => ({ ...previous, [id]: { status: 'ready', generation } }));
    } catch (caught) {
      setExplanations((previous) => ({
        ...previous,
        [id]: { status: 'error', message: describeApiError(caught, 'Could not explain this priority.') },
      }));
    }
  };

  // Started from the click, not an effect: one press is one model call.
  const openExplain = (item: PriorityScore) => {
    setExplainId(item.entity_id);
    const existing = explanations[item.entity_id];
    if (aiReady && canUseAi && (!existing || existing.status === 'error')) {
      void requestExplanation(item);
    }
  };

  /* ---- Take action ---- */
  const [action, setAction] = useState<ActionState | null>(null);
  const [preparing, setPreparing] = useState(false);

  const takeAction = async (kind: NbaActionKind, item: PriorityScore) => {
    setExplainId(null);
    if (kind !== 'email') {
      setAction({ kind, item });
      return;
    }
    if (item.entity_type === 'LEAD') {
      setAction({ kind, item, to: item.facts.email });
      return;
    }
    // A deal's recipient is its primary contact — read through the contact's
    // own endpoint, so its visibility applies. Any failure leaves "To" blank.
    setPreparing(true);
    let to: string | null = null;
    try {
      const opportunity = await getOpportunity(item.entity_id);
      if (opportunity.primary_contact_id) to = (await getContact(opportunity.primary_contact_id)).email;
    } catch {
      to = null;
    } finally {
      setPreparing(false);
    }
    setAction({ kind, item, to });
  };

  const closeAction = () => setAction(null);

  /* ---- Render ---- */
  const shown = filtered.slice(0, visible);
  const loadedAt = data?.loadedAt ?? null;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-4 sm:p-6 lg:p-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3.5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-600">
            <Zap className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="txt-faint text-[11px] font-bold uppercase tracking-wider">AI Sales Intelligence</p>
            <h1 className="font-display txt text-[22px] font-extrabold leading-tight sm:text-[24px]">
              Next Best Action
            </h1>
            <p className="txt-muted mt-0.5 text-[13px]">AI-powered recommendations for what to work on next.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 sm:pt-1">
          <NbaAiStatusPill status={status} error={statusError} loading={statusLoading} />
          <button
            type="button"
            onClick={reload}
            disabled={refreshing || (!data && !loadError)}
            aria-label="Refresh the queue"
            title="Refresh the queue"
            className="ctl grid h-8 w-8 place-items-center transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'motion-safe:animate-spin' : ''}`} aria-hidden="true" />
          </button>
        </div>
      </header>

      <AiConnectionNotice
        status={status}
        error={statusError}
        hideWhenReady
        compact
        consequence="The ranked queue below still works — it is computed from CRM fields, not the model. Stored recommendations still show; generating a new one or an explanation needs the AI connection."
      />

      {!data && loadError && <ListError message={loadError} onRetry={reload} />}
      {!data && !loadError && <QueueSkeleton />}

      {data && loadedAt && (
        <>
          <NbaKpiStrip kpis={kpis} active={activeShortcut} onShortcut={(key) => changeFilters(SHORTCUT_FILTERS[key])} />

          {loadError && (
            <p role="alert" className="text-[12.5px] text-rose-600">
              Showing the last loaded queue — the refresh failed: {loadError}
            </p>
          )}

          <section aria-labelledby="nba-queue-heading" className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2 id="nba-queue-heading" className="txt font-display text-[16px] font-bold">
                  Recommended actions
                </h2>
                <p className="txt-muted text-[12.5px]">Highest priority first — work down from the top.</p>
              </div>
              {preparing && (
                <p role="status" className="txt-muted flex items-center gap-1.5 text-[12px]">
                  <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> Opening the
                  composer…
                </p>
              )}
            </div>

            <NbaQueueToolbar
              filters={filters}
              onChange={changeFilters}
              scopeCounts={scopeCounts}
              signalCounts={signalCounts}
              availableSignals={availableSignals}
              shown={filtered.length}
              total={inScope.length}
            />

            {queue.length === 0 ? (
              <div className="surface bd rounded-2xl border">
                <AiEmptyState
                  icon={Sparkles}
                  title="Nothing open to prioritize"
                  description="Open deals and active leads you can see appear here, ranked, as soon as they exist."
                />
              </div>
            ) : filtered.length === 0 ? (
              <div className="surface bd rounded-2xl border">
                <AiEmptyState
                  icon={SearchX}
                  title="No records match these filters"
                  description="Clear a filter or switch record type to see more of the queue."
                  action={
                    <button
                      type="button"
                      onClick={() => changeFilters(EMPTY_FILTERS)}
                      className="rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
                      style={{ background: 'var(--accent)' }}
                    >
                      Clear filters
                    </button>
                  }
                />
              </div>
            ) : (
              <ol className="space-y-3">
                {shown.map((item) => (
                  <li key={item.entity_id}>
                    <NbaQueueCard
                      item={item}
                      rank={rankOf.get(item.entity_id) ?? 0}
                      now={loadedAt}
                      canGenerate={aiReady && canUseAi}
                      generating={generating.has(item.entity_id)}
                      generateError={generateErrors[item.entity_id] ?? null}
                      onGenerate={() => void generate(item)}
                      onExplain={() => openExplain(item)}
                      onAction={(kind, target) => void takeAction(kind, target)}
                    />
                  </li>
                ))}
              </ol>
            )}

            {filtered.length > shown.length && (
              <div className="flex justify-center pt-1">
                <button
                  type="button"
                  onClick={() => setVisible((count) => count + PAGE_SIZE)}
                  className="ctl px-4 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
                >
                  Show {Math.min(PAGE_SIZE, filtered.length - shown.length)} more
                </button>
              </div>
            )}
          </section>
        </>
      )}

      <p className="txt-faint flex items-start gap-1.5 text-[11.5px]">
        <Sparkles className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        Ranked by deal size, close date, win probability, recent activity and overdue tasks. Recommendations and
        explanations are generated only when requested, and always show when they were generated.
      </p>

      <NbaExplainDrawer
        item={explainItem}
        rank={explainItem ? (rankOf.get(explainItem.entity_id) ?? null) : null}
        now={loadedAt ?? EPOCH}
        explanation={explainItem ? (explanations[explainItem.entity_id] ?? null) : null}
        onExplain={() => explainItem && void requestExplanation(explainItem)}
        aiStatus={status}
        aiError={statusError}
        aiReady={aiReady}
        canUseAi={canUseAi}
        generating={explainItem ? generating.has(explainItem.entity_id) : false}
        generateError={explainItem ? (generateErrors[explainItem.entity_id] ?? null) : null}
        onGenerate={() => explainItem && void generate(explainItem)}
        onAction={(kind, target) => void takeAction(kind, target)}
        onClose={() => setExplainId(null)}
      />

      <NbaTaskDrawer item={action?.kind === 'task' ? action.item : null} onClose={closeAction} onSaved={reload} />
      <NbaMeetingDrawer item={action?.kind === 'meeting' ? action.item : null} onClose={closeAction} onSaved={reload} />
      <ComposeEmailDrawer
        open={action?.kind === 'email'}
        onClose={closeAction}
        entityType={action?.item.entity_type ?? null}
        entityId={action?.item.entity_id ?? null}
        defaultTo={action?.kind === 'email' ? action.to : null}
        onSent={reload}
      />
    </div>
  );
}
