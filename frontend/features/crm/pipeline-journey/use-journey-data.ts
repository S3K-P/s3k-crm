'use client';

import {
  JOURNEY_ATTENTION,
  JOURNEY_FUNNEL_STATS,
  JOURNEY_GOAL,
  JOURNEY_HERO,
  JOURNEY_KPIS,
  JOURNEY_MOMENTUM,
  JOURNEY_STAGES,
  JOURNEY_TOTALS,
} from './data';
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
   The page's single data seam. Today it hands back the mock
   module synchronously; point it at the pipeline endpoint and
   the page's loading / empty branches start firing on their own
   because the shape it returns does not change.
   ============================================================ */

export interface JourneyData {
  status: JourneyStatus;
  totals: JourneyTotals;
  hero: JourneyHeroContent;
  kpis: JourneyKpi[];
  stages: JourneyStage[];
  funnelStats: JourneyFunnelStat[];
  goal: JourneyGoal;
  momentum: MomentumMetric[];
  attention: AttentionItem[];
}

export function useJourneyData(): JourneyData {
  // An account with nothing in flight gets the empty state rather than a
  // funnel of zeroes — the same check the real response will need.
  const hasPipeline = JOURNEY_STAGES.some(stage => stage.count > 0);

  return {
    status: hasPipeline ? 'ready' : 'empty',
    totals: JOURNEY_TOTALS,
    hero: JOURNEY_HERO,
    kpis: JOURNEY_KPIS,
    stages: JOURNEY_STAGES,
    funnelStats: JOURNEY_FUNNEL_STATS,
    goal: JOURNEY_GOAL,
    momentum: JOURNEY_MOMENTUM,
    attention: JOURNEY_ATTENTION,
  };
}
