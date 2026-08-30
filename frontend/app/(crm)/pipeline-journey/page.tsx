'use client';

import { useState } from 'react';
import {
  JourneyDealsDrawer,
  JourneyEmptyState,
  JourneyFunnel,
  JourneyHero,
  JourneyKpiRow,
  JourneySkeleton,
  JourneyUnavailable,
  useCountUp,
  useJourneyData,
  type JourneyFocusId,
} from '@/features/crm/pipeline-journey';

/* ============================================================
   PIPELINE JOURNEY PAGE
   The story of the funnel on one screen: where the money is and
   how it is distributed across the stages this organization
   actually uses.

   Every stage row opens the same drawer, focused on that cut of
   the pipeline — so the page never navigates away from the
   narrative to answer "which deals?".

   Panels whose figures the CRM cannot yet compute (momentum,
   the attention queue, the revenue goal) render as explicitly
   unavailable rather than being filled with plausible numbers.
   See `use-journey-data.ts` for what each one is waiting on.
   ============================================================ */

export default function PipelineJourneyPage() {
  const journey = useJourneyData();
  const progress = useCountUp();

  /** Which cut of the pipeline the drawer is showing; `null` = closed. */
  const [focus, setFocus] = useState<JourneyFocusId | null>(null);

  if (journey.status === 'loading') return <JourneySkeleton />;

  if (journey.status === 'error') {
    return (
      <div className="flex max-w-[1520px] flex-col gap-5 p-6 lg:p-8">
        <JourneyUnavailable
          title="Pipeline could not be loaded"
          detail={journey.error ?? 'Something went wrong.'}
          onRetry={journey.reload}
        />
      </div>
    );
  }

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

        <JourneyKpiRow
          kpis={journey.kpis}
          totals={journey.totals}
          split={journey.stages}
          progress={progress}
        />

        <section className="grid items-start gap-5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,470px),1fr))]">
          <JourneyFunnel
            stages={journey.stages}
            stats={journey.funnelStats}
            openDeals={journey.totals.openDeals}
            tooltipsEnabled={focus === null}
            onOpenStage={setFocus}
          />

          <div className="flex flex-col gap-5">
            <JourneyUnavailable
              title="Revenue goal"
              detail="The CRM has no revenue target to measure against. This panel turns on once a quarterly goal can be set."
            />
            <JourneyUnavailable
              title="Pipeline momentum"
              detail="Week-over-week creation, movement and stall rates need a historical aggregate the API does not expose yet."
            />
          </div>
        </section>

        <JourneyUnavailable
          title="What needs attention"
          detail="Stalled and closing-soon deals need per-deal stage-entry timestamps, which are recorded but not yet aggregated."
        />
      </div>

      <JourneyDealsDrawer
        focus={focus}
        stages={journey.stages}
        onClose={() => setFocus(null)}
      />
    </>
  );
}
