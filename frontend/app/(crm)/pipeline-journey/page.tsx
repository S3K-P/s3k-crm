'use client';

import { useState } from 'react';
import {
  JourneyAttention,
  JourneyDealsDrawer,
  JourneyEmptyState,
  JourneyFunnel,
  JourneyGoalCard,
  JourneyHero,
  JourneyKpiRow,
  JourneyMomentumCard,
  JourneySkeleton,
  useCountUp,
  useJourneyData,
  type JourneyFocusId,
} from '@/features/crm/pipeline-journey';

/* ============================================================
   PIPELINE JOURNEY PAGE
   The story of the funnel on one screen: where the money is,
   which way it is moving, and what to do about it next.

   Every stage row and attention card opens the same drawer,
   focused on that cut of the pipeline — so the page never
   navigates away from the narrative to answer "which deals?".
   ============================================================ */

export default function PipelineJourneyPage() {
  const journey = useJourneyData();
  const progress = useCountUp();

  /** Which cut of the pipeline the drawer is showing; `null` = closed. */
  const [focus, setFocus] = useState<JourneyFocusId | null>(null);

  if (journey.status === 'loading') return <JourneySkeleton />;
  if (journey.status === 'empty') return <JourneyEmptyState />;

  return (
    <>
      <div className="flex max-w-[1520px] flex-col gap-5 p-6 lg:p-8">
        <JourneyHero
          content={journey.hero}
          totals={journey.totals}
          goal={journey.goal}
          progress={progress}
          onOpenClosing={() => setFocus('closing')}
        />

        <JourneyKpiRow kpis={journey.kpis} totals={journey.totals} progress={progress} />

        <section className="grid items-start gap-5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,470px),1fr))]">
          <JourneyFunnel
            stages={journey.stages}
            stats={journey.funnelStats}
            openDeals={journey.totals.openDeals}
            tooltipsEnabled={focus === null}
            onOpenStage={setFocus}
          />

          <div className="flex flex-col gap-5">
            <JourneyGoalCard goal={journey.goal} totals={journey.totals} progress={progress} />
            <JourneyMomentumCard metrics={journey.momentum} />
          </div>
        </section>

        <JourneyAttention items={journey.attention} onOpenPreset={setFocus} />
      </div>

      <JourneyDealsDrawer focus={focus} onClose={() => setFocus(null)} />
    </>
  );
}
