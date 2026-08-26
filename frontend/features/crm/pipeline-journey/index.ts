// features/crm/pipeline-journey — barrel export
// Pipeline Journey feature module: the narrative funnel view —
// hero, KPIs, tapering stage funnel, quarterly goal, momentum,
// the AI attention queue and the filtered deals drawer.

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

export { useJourneyData, type JourneyData } from './use-journey-data';
export { useCountUp } from './use-count-up';
export { getFocusDeals, getFocusMeta } from './data';

export type * from './types';
