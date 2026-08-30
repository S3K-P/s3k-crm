'use client';

import { ShieldCheck, Target, TrendingUp, Wallet, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatMoney } from '@/features/crm/dashboard/presenters';
import type { JourneyKpi, JourneyTotals } from '../types';

/* ============================================================
   JOURNEY KPI ROW
   Four headline metrics. Each card carries its own miniature
   chart — a creation sparkline, the stage split, and two
   progress meters — so the number is never the only signal.
   Values animate up off the shared counter progress.
   ============================================================ */

interface JourneyKpiRowProps {
  kpis: JourneyKpi[];
  totals: JourneyTotals;
  /** The funnel's real stages, driving the split bar on the deals card. */
  split: { id: string; count: number }[];
  /** 0 → 1 counter progress shared with the hero */
  progress: number;
}

const ICONS: Record<JourneyKpi['id'], LucideIcon> = {
  // Currency-neutral: the pipeline is not necessarily denominated in rupees.
  pipeline: Wallet,
  deals: Target,
  winRate: TrendingUp,
  goal: ShieldCheck,
};

/**
 * Colour ramp for the stage-split bar, sampled by position.
 *
 * The split itself is built from the funnel's real stage counts — it used to
 * be a hardcoded `[142, 65, 38, 18]`, which drew the same four segments for
 * every organization regardless of its actual pipeline.
 *
 * The weekly creation sparkline that sat beside it has been removed outright
 * rather than nulled: it was seven invented bars, and there is no
 * pipeline-creation history to plot in its place.
 */
const SPLIT_COLORS = ['#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe', '#34d399'];

export default function JourneyKpiRow({ kpis, totals, split, progress }: JourneyKpiRowProps) {
  // Formatted in the organization's own currency rather than a hardcoded
  // ₹/crore. `null` figures render as an em dash: the card still explains
  // what it would show, but never states a number nobody computed.
  const values: Record<JourneyKpi['id'], string> = {
    pipeline: formatMoney(String(totals.pipelineValue * progress), totals.currency),
    deals: String(Math.round(totals.openDeals * progress)),
    winRate:
      totals.winRatePct === null ? '—' : `${Math.round(totals.winRatePct * progress)}%`,
    goal: totals.goalPct === null ? '—' : `${Math.round(totals.goalPct * progress)}%`,
  };

  return (
    <section className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(230px,1fr))]">
      {kpis.map((kpi, i) => {
        const Icon = ICONS[kpi.id];

        return (
          <div
            key={kpi.id}
            className="surface bd anim-fade-up rounded-[20px] border p-5 transition-transform duration-200 hover:-translate-y-[3px]"
            style={{
              boxShadow: 'var(--shadow-card)',
              animationDelay: `${0.06 * (i + 1)}s`,
            }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="txt-muted text-[12px] font-bold uppercase tracking-[0.07em]">
                  {kpi.label}
                </p>
                <p className="txt font-display mt-2.5 text-[30px] font-extrabold leading-none tracking-[-0.03em] tabular-nums">
                  {values[kpi.id]}
                </p>
                <p
                  className={cn(
                    'mt-[9px] text-[11.5px] font-bold',
                    kpi.deltaTone === 'positive' && 'text-emerald-600 dark:text-emerald-400',
                  )}
                  style={kpi.deltaTone === 'accent' ? { color: 'var(--accent)' } : undefined}
                >
                  {kpi.delta}
                </p>
              </div>
              <div
                className={cn(
                  'grid h-[42px] w-[42px] shrink-0 place-items-center rounded-[13px] bg-gradient-to-br',
                  kpi.iconGradient,
                )}
              >
                <Icon className="h-5 w-5 text-white" strokeWidth={1.9} />
              </div>
            </div>

            {/* ── Per-card mini chart ── */}
            {kpi.id === 'deals' && split.length > 0 && (
              <div className="mt-3.5 flex gap-1">
                {split.map((segment, index) => (
                  <div
                    key={segment.id}
                    className="h-[7px] rounded-full"
                    style={{
                      flex: Math.max(segment.count, 1),
                      background: SPLIT_COLORS[index % SPLIT_COLORS.length],
                    }}
                  />
                ))}
              </div>
            )}

            {/* A meter is only drawn when there is a figure behind it. An
                empty track at 0% reads as "we measured zero"; no track at
                all reads as "not measured", which is the truth here. */}
            {(kpi.id === 'winRate' || kpi.id === 'goal') &&
              (kpi.id === 'winRate' ? totals.winRatePct : totals.goalPct) !== null && (
                <div className="surface-2 mt-4 h-[7px] overflow-hidden rounded-full">
                  <div
                    className={cn(
                      'anim-bar-grow h-full rounded-full bg-gradient-to-r',
                      kpi.id === 'winRate'
                        ? 'from-emerald-500 to-emerald-400'
                        : 'from-[color:var(--accent)] to-[color:var(--accent-2)]',
                    )}
                    style={{
                      width: `${kpi.id === 'winRate' ? totals.winRatePct : totals.goalPct}%`,
                      animationDelay: kpi.id === 'winRate' ? '0.4s' : '0.45s',
                    }}
                  />
                </div>
              )}

            <p className="txt-faint mt-2 text-[11px] font-semibold">{kpi.caption}</p>
          </div>
        );
      })}
    </section>
  );
}
