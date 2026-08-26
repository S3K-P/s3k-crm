'use client';

import Link from 'next/link';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { getFocusDeals, getFocusMeta } from '../data';
import type { JourneyFocusId } from '../types';

/* ============================================================
   JOURNEY DEALS DRAWER
   The filtered opportunity list behind every stage row and
   attention card. Built on the shared CRM SlideDrawer so it
   opens, closes and traps ESC exactly like the rest of the app.
   ============================================================ */

interface JourneyDealsDrawerProps {
  /** `null` keeps the drawer closed */
  focus: JourneyFocusId | null;
  onClose: () => void;
}

export default function JourneyDealsDrawer({ focus, onClose }: JourneyDealsDrawerProps) {
  const meta = focus ? getFocusMeta(focus) : null;
  const deals = focus ? getFocusDeals(focus) : [];

  return (
    <SlideDrawer
      open={focus !== null}
      onClose={onClose}
      title={meta?.title ?? ''}
      subtitle={meta?.subtitle}
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

        {deals.map(deal => (
          <div
            key={deal.id}
            className="surface-2 bd rounded-[18px] border px-4 py-[15px] transition-[transform,border-color] duration-200 hover:-translate-x-[3px] hover:border-[color:var(--accent)]"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="txt text-[13.5px] font-bold tracking-[-0.01em]">{deal.account}</div>
                <div className="txt-muted mt-[3px] text-[12px] font-medium">{deal.name}</div>
              </div>
              <div className="txt font-display shrink-0 text-[16px] font-extrabold tracking-[-0.02em]">
                {deal.value}
              </div>
            </div>

            <div className="mt-[11px] flex flex-wrap items-center gap-2">
              <span
                className="rounded-full px-[9px] py-[3px] text-[11px] font-bold"
                style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
              >
                {deal.stage}
              </span>
              <span className="txt-faint text-[11.5px] font-semibold">{deal.owner}</span>
              <span className="txt-faint text-[11.5px] font-semibold">· {deal.age}</span>
              <span className="txt-muted ml-auto text-[11.5px] font-bold">{deal.note}</span>
            </div>
          </div>
        ))}
      </div>
    </SlideDrawer>
  );
}
