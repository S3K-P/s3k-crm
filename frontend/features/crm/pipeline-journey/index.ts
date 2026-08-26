// features/crm/pipeline-journey — barrel export
// Pipeline Journey feature module: the narrative funnel view — hero, KPIs,
// the tapering stage funnel and the filtered deals drawer, all read from the
// organization's real pipeline.
//
// `JourneyGoalCard`, `JourneyMomentumCard` and `JourneyAttention` are still
// exported but are not mounted by the page: each needs an aggregate the API
// does not expose, and the page renders `JourneyUnavailable` in their place
// rather than filling them with plausible figures. They are kept because the
// markup is finished and correct — only the data is missing — so wiring them
// up later is a matter of supplying props, not rebuilding the panels.

export { default as JourneyHero } from './components/JourneyHero';
export { default as JourneyKpiRow } from './components/JourneyKpiRow';
export { default as JourneyFunnel } from './components/JourneyFunnel';
export { default as JourneyStageRow } from './components/JourneyStageRow';
export { default as JourneyGoalCard } from './components/JourneyGoalCard';
export { default as JourneyMomentumCard } from './components/JourneyMomentumCard';
export { default as JourneyAttention } from './components/JourneyAttention';
export { default as JourneyDealsDrawer } from './components/JourneyDealsDrawer';
export { default as JourneySkeleton } from './components/JourneySkeleton';
export { default as JourneyEmptyState } from './components/JourneyEmptyState';
export { default as JourneyUnavailable } from './components/JourneyUnavailable';

export { useJourneyData, type JourneyData } from './use-journey-data';
export { useCountUp } from './use-count-up';
export { getFocusMeta } from './data';
export {
  fetchDashboard,
  fetchLeadTotal,
  fetchStageDeals,
  fetchStages,
  type PipelineStage,
  type StageDeal,
} from './api';

export type * from './types';
