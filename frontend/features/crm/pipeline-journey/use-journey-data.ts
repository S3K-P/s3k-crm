'use client';

import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import { formatMoney } from '@/features/crm/dashboard/presenters';
import type { DashboardSummary } from '@/features/crm/dashboard/types';

import { fetchDashboard, fetchLeadTotal, fetchStages, type PipelineStage } from './api';
import { decorateStage } from './data';
import { LEADS_ROW_ID } from './types';
import type {
  AttentionItem,
  JourneyFunnelStat,
  JourneyGoal,
  JourneyHeroContent,
  JourneyKpi,
  JourneyStage,
  JourneyStatus,
  JourneyTotals,
  MomentumMetric,
} from './types';

/* ============================================================
   useJourneyData

   The page's single data seam, now reading the organization's
   real pipeline.

   ── WHAT IS REAL ───────────────────────────────────────────
   Every figure this returns comes from rows in the caller's
   organization, resolved through the same endpoints — and
   therefore the same permission and record-visibility rules —
   as the dashboard and the opportunity list:

     funnel rows      real pipeline stages, with their real open
                      counts and summed deal values
     leads row        the real lead total
     open pipeline    dashboard `pipeline_value`
     active deals     dashboard `open_opportunities`
     weighted forecast Σ (stage value × stage win probability)
     average deal size pipeline value ÷ open deals

   ── WHAT IS NOT AVAILABLE, AND WHY IT IS NULL ──────────────
   The rest of the page's panels want figures the CRM cannot
   currently answer. They are returned as `null` and rendered as
   unavailable, rather than estimated:

     win rate         needs won-vs-lost counts over closed deals
     conversion %     needs an aggregate over stage history
     week deltas      needs a prior snapshot to compare against
     momentum         same — creation, movement and stall rates
                      are time-series questions
     stalled deals    needs per-deal stage-entry timestamps
     revenue goal     the schema has no revenue target at all

   Showing a plausible number for any of these would put an
   invented figure beside real ones under a live login, which is
   precisely what `useDashboardSummary` refuses to do and what
   CR06 exists to prevent. A page that says "not available yet"
   is less impressive and considerably more useful.
   ============================================================ */

export type { JourneyStatus } from './types';

export interface JourneyData {
  status: JourneyStatus | 'error';
  totals: JourneyTotals;
  hero: JourneyHeroContent;
  kpis: JourneyKpi[];
  stages: JourneyStage[];
  funnelStats: JourneyFunnelStat[];
  /** `null` while the CRM has no revenue-target model. */
  goal: JourneyGoal | null;
  /** Empty while momentum has no backing aggregate. */
  momentum: MomentumMetric[];
  /** Empty while the attention queue has no backing aggregate. */
  attention: AttentionItem[];
  error: string | null;
  reload: () => void;
}

interface Loaded {
  key: string;
  summary: DashboardSummary | null;
  stages: PipelineStage[];
  leadTotal: number | null;
  error: string | null;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'You do not have permission to view the pipeline in this organization.';
    }
    return error.message;
  }
  if (error instanceof TypeError) {
    return 'Could not reach the API. Check that the backend is running.';
  }
  return 'Something went wrong loading the pipeline.';
}

const EMPTY_TOTALS: JourneyTotals = {
  pipelineValue: 0,
  currency: null,
  openDeals: 0,
  winRatePct: null,
  goalPct: null,
};

export function useJourneyData(): JourneyData {
  const { loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();
  const [result, setResult] = useState<Loaded | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt(n => n + 1), []);

  // Same staleness guard as `useDashboardSummary`: a response is stamped with
  // the request it answered, so a slow reply for the previous organization
  // can never repaint this page with another tenant's pipeline.
  const key = `${activeOrganizationId ?? 'none'}#${attempt}`;

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;

    const controller = new AbortController();

    void (async () => {
      try {
        // In parallel: three independent reads, one round trip's latency.
        const [summary, stages, leadTotal] = await Promise.all([
          fetchDashboard(controller.signal),
          fetchStages(controller.signal),
          fetchLeadTotal(controller.signal).catch(() => null),
        ]);
        if (!controller.signal.aborted) {
          setResult({ key, summary, stages, leadTotal, error: null });
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setResult({ key, summary: null, stages: [], leadTotal: null, error: describe(caught) });
        }
      }
    })();

    return () => controller.abort();
  }, [authLoading, isAuthenticated, key]);

  const current = result?.key === key ? result : null;

  if (current === null) {
    return blank('loading', null, reload);
  }
  if (current.error !== null) {
    return blank('error', current.error, reload);
  }

  return build(current, reload);
}

function blank(
  status: JourneyData['status'],
  error: string | null,
  reload: () => void,
): JourneyData {
  return {
    status,
    totals: EMPTY_TOTALS,
    hero: heroFor(null),
    kpis: [],
    stages: [],
    funnelStats: [],
    goal: null,
    momentum: [],
    attention: [],
    error,
    reload,
  };
}

function build(loaded: Loaded, reload: () => void): JourneyData {
  const summary = loaded.summary!;
  const currency = summary.pipeline_currency;
  const pipelineValue = Number(summary.pipeline_total) || 0;
  const openDeals = summary.kpis.open_opportunities;

  // Probability per stage, for the weighted forecast. Keyed by id because
  // stage names are tenant-defined and can repeat across pipelines.
  const probability = new Map(loaded.stages.map(s => [s.id, s.default_probability]));

  // The funnel, top to bottom: leads first when we could count them, then the
  // organization's own open stages in their configured order.
  const core = [
    ...(loaded.leadTotal === null
      ? []
      : [
          {
            id: LEADS_ROW_ID,
            label: 'Leads',
            count: loaded.leadTotal,
            // Leads carry `expected_deal_size`, but nothing aggregates it, so
            // the top row is a count without a value rather than a count
            // beside a guess.
            value: '—',
            conversion: null,
            movement: null,
          },
        ]),
    ...summary.pipeline.map(stage => ({
      id: stage.stage_id,
      label: stage.name,
      count: stage.count,
      value: formatMoney(String(stage.value), currency),
      conversion: null,
      movement: null,
    })),
  ];

  // Geometry is derived from position, not hardcoded per stage — the row count
  // is whatever the tenant configured.
  const stages: JourneyStage[] = core.map((row, index) =>
    decorateStage(row, index, core.length),
  );

  const hasPipeline = openDeals > 0 || summary.pipeline.some(s => s.count > 0);

  return {
    status: hasPipeline ? 'ready' : 'empty',
    totals: {
      pipelineValue,
      currency,
      openDeals,
      winRatePct: null,
      goalPct: null,
    },
    hero: heroFor(summary),
    kpis: kpisFor(summary),
    stages,
    funnelStats: funnelStatsFor(summary, probability, currency),
    goal: null,
    momentum: [],
    attention: [],
    error: null,
    reload,
  };
}

/**
 * Hero copy.
 *
 * The greeting and the period line are computed from the clock, which is real.
 * The month-over-month delta, the goal caption and the "best next move" are
 * left empty — each needed a comparison or a recommendation engine that does
 * not exist, and an empty string renders as nothing rather than as a claim.
 */
function heroFor(summary: DashboardSummary | null): JourneyHeroContent {
  const now = new Date();
  const quarter = Math.floor(now.getMonth() / 3) + 1;
  const periodLine = `Q${quarter} ${now.getFullYear()}`;

  return {
    periodLine,
    pipelineDelta: '',
    goalCaption: '',
    nextMove: '',
    nextMoveCta: '',
    tiles: summary
      ? [
          {
            id: 'closing',
            value: String(summary.kpis.opportunities_closing_soon),
            label: 'Closing in 30 days',
          },
          {
            id: 'qualified',
            value: String(summary.kpis.qualified_leads),
            label: 'Qualified leads',
          },
        ]
      : [],
  };
}

/** The KPI strip. Only the two cards with real figures are returned. */
function kpisFor(summary: DashboardSummary): JourneyKpi[] {
  return [
    {
      id: 'pipeline',
      label: 'Pipeline value',
      delta: '',
      deltaTone: 'accent',
      caption: `${summary.pipeline.length} open ${
        summary.pipeline.length === 1 ? 'stage' : 'stages'
      }`,
      iconGradient: 'from-violet-600 to-purple-600',
    },
    {
      id: 'deals',
      label: 'Active deals',
      delta: '',
      deltaTone: 'accent',
      caption: `${summary.kpis.opportunities_closing_soon} closing within 30 days`,
      iconGradient: 'from-violet-700 to-violet-600',
    },
  ];
}

/**
 * The strip under the funnel.
 *
 * Both figures are derived arithmetic over real values, not estimates:
 * the forecast weights each stage's own value by that stage's own configured
 * probability, and the average is a division. Neither invents an input.
 */
function funnelStatsFor(
  summary: DashboardSummary,
  probability: Map<string, number | null>,
  currency: string | null,
): JourneyFunnelStat[] {
  const weighted = summary.pipeline.reduce((total, stage) => {
    const chance = probability.get(stage.stage_id);
    if (chance === null || chance === undefined) return total;
    return total + (Number(stage.value) || 0) * (chance / 100);
  }, 0);

  const openDeals = summary.kpis.open_opportunities;
  const average = openDeals > 0 ? (Number(summary.pipeline_total) || 0) / openDeals : 0;

  const stats: JourneyFunnelStat[] = [];

  // Omitted rather than shown as zero when no stage carries a probability:
  // a forecast of ₹0 reads as "nothing will close", not as "unconfigured".
  const anyProbability = summary.pipeline.some(s => {
    const chance = probability.get(s.stage_id);
    return chance !== null && chance !== undefined;
  });
  if (anyProbability) {
    stats.push({
      id: 'forecast',
      label: 'Weighted forecast',
      value: formatMoney(String(weighted), currency),
    });
  }

  if (openDeals > 0) {
    stats.push({
      id: 'average',
      label: 'Avg. deal size',
      value: formatMoney(String(average), currency),
    });
  }

  return stats;
}
