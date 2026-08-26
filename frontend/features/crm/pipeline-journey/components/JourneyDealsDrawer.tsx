'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Loader2 } from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { formatMoney } from '@/features/crm/dashboard/presenters';

import { fetchStageDeals, type StageDeal } from '../api';
import { getFocusMeta } from '../data';
import type { JourneyFocusId, JourneyStage } from '../types';

/* ============================================================
   JOURNEY DEALS DRAWER

   The filtered opportunity list behind every stage row. Built on
   the shared CRM SlideDrawer so it opens, closes and traps ESC
   exactly like the rest of the app.

   Deals are fetched from `/crm/opportunities` filtered to the
   stage, on open — not held in the page. They used to come from
   a hardcoded map keyed by five fixed stage names, which meant
   the drawer showed the same four invented deals to every
   organization, and showed nothing at all to any tenant whose
   stages were named differently.

   Fetching on open rather than up front keeps the page's initial
   load to the three requests it needs; a drawer nobody opens
   costs nothing.
   ============================================================ */

/** Enough to see the shape of a stage without paging. */
const DRAWER_LIMIT = 25;

interface JourneyDealsDrawerProps {
  /** `null` keeps the drawer closed */
  focus: JourneyFocusId | null;
  /** The funnel's rows, for resolving the focused stage's header copy */
  stages: JourneyStage[];
  onClose: () => void;
}

export default function JourneyDealsDrawer({
  focus,
  stages,
  onClose,
}: JourneyDealsDrawerProps) {
  const stage = stages.find(row => row.id === focus);
  const meta = getFocusMeta(stage);

  // The leads row has no opportunities behind it — it counts a different
  // table — so there is nothing to fetch for it.
  const fetchable = focus !== null && stage !== undefined && stage.id !== 'leads';

  /**
   * Which stage the drawer should currently be showing.
   *
   * Results are stamped with the request they answered, so reopening the
   * drawer on a different stage shows the loading state rather than the
   * previous stage's deals, and a slow reply for a stage the user has already
   * navigated away from is ignored on arrival. Same guard as
   * `useDashboardSummary`, for the same reason — and it means "loading" is
   * *derived* from the mismatch rather than being a third piece of state set
   * synchronously at the top of an effect.
   */
  const key = fetchable ? stage.id : null;
  const [result, setResult] = useState<{ key: string; deals: StageDeal[] | null } | null>(
    null,
  );

  useEffect(() => {
    if (key === null) return;

    const controller = new AbortController();

    fetchStageDeals(key, DRAWER_LIMIT, controller.signal)
      .then(page => {
        if (!controller.signal.aborted) setResult({ key, deals: page.data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ key, deals: null });
      });

    return () => controller.abort();
  }, [key]);

  const current = result?.key === key ? result : null;
  const loading = key !== null && current === null;
  const failed = current !== null && current.deals === null;
  const visible = current?.deals ?? [];

  return (
    <SlideDrawer
      open={focus !== null}
      onClose={onClose}
      title={meta.title}
      subtitle={meta.subtitle}
      width="max-w-[480px]"
      footer={
        <>
          <Link
            href="/opportunities"
            className="flex-1 rounded-xl py-[11px] text-center text-[13px] font-bold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            Open in Opportunities
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="ctl px-[18px] py-[11px] text-[13px] font-semibold transition hover:opacity-80"
          >
            Close
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-2.5">
        <p
          className="text-[11px] font-bold uppercase tracking-[0.09em]"
          style={{ color: 'var(--accent)' }}
        >
          Opportunities · filtered
        </p>

        {loading && (
          <div className="txt-faint flex items-center gap-2 py-8 text-[12.5px]">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Loading opportunities…
          </div>
        )}

        {failed && !loading && (
          <p className="txt-faint py-8 text-center text-[12.5px]">
            Could not load opportunities for this stage.
          </p>
        )}

        {!loading && !failed && visible.length === 0 && (
          <p className="txt-faint py-8 text-center text-[12.5px]">
            {stage?.id === 'leads'
              ? 'Leads are not opportunities — open the Leads page to work this stage.'
              : 'No open opportunities in this stage.'}
          </p>
        )}

        {!loading &&
          visible.map(deal => (
            <Link
              key={deal.id}
              href={`/opportunities/${deal.id}`}
              className="surface-2 bd block rounded-[18px] border px-4 py-[15px] transition-[transform,border-color] duration-200 hover:-translate-x-[3px] hover:border-[color:var(--accent)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="txt truncate text-[13.5px] font-bold tracking-[-0.01em]">
                    {deal.name}
                  </div>
                </div>
                <div className="txt font-display shrink-0 text-[16px] font-extrabold tracking-[-0.02em]">
                  {deal.deal_value === null
                    ? '—'
                    : formatMoney(deal.deal_value, deal.currency)}
                </div>
              </div>

              <div className="mt-[11px] flex flex-wrap items-center gap-2">
                <span
                  className="rounded-full px-[9px] py-[3px] text-[11px] font-bold"
                  style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
                >
                  {stage?.label ?? 'Open'}
                </span>
                {deal.win_probability !== null && (
                  <span className="txt-faint text-[11.5px] font-semibold">
                    {deal.win_probability}% probability
                  </span>
                )}
                {deal.expected_close_date && (
                  <span className="txt-muted ml-auto text-[11.5px] font-bold">
                    Closes {new Date(deal.expected_close_date).toLocaleDateString()}
                  </span>
                )}
              </div>
            </Link>
          ))}
      </div>
    </SlideDrawer>
  );
}
