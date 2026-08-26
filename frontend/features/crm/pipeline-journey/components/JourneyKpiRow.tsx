'use client';

import { IndianRupee, ShieldCheck, Target, TrendingUp, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
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
  /** 0 → 1 counter progress shared with the hero */
  progress: number;
}

const ICONS: Record<JourneyKpi['id'], LucideIcon> = {
  pipeline: IndianRupee,
  deals: Target,
  winRate: TrendingUp,
  goal: ShieldCheck,
};

/** Weekly pipeline-creation sparkline, oldest → newest. */
const SPARK_BARS = [38, 52, 44, 70, 62, 88, 100];

/** Open deals per stage, driving the flex ratios of the split bar. */
const STAGE_SPLIT = [
  { count: 142, color: '#8b5cf6' },
  { count: 65, color: '#a78bfa' },
  { count: 38, color: '#c4b5fd' },
  { count: 18, color: '#34d399' },
];

export default function JourneyKpiRow({ kpis, totals, progress }: JourneyKpiRowProps) {
  const values: Record<JourneyKpi['id'], string> = {
    pipeline: `₹${(totals.pipelineCr * progress).toFixed(2)}Cr`,
    deals: String(Math.round(totals.openDeals * progress)),
    winRate: `${Math.round(totals.winRatePct * progress)}%`,
    goal: `${Math.round(totals.goalPct * progress)}%`,
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
            {kpi.id === 'pipeline' && (
              <div className="mt-3.5 flex h-[26px] items-end gap-[3px]">
                {SPARK_BARS.map((height, bar) => (
                  <div
                    key={bar}
                    className="anim-spark flex-1 rounded-[3px]"
                    style={{
                      height: `${height}%`,
                      background: bar < 4 ? 'var(--accent-soft)' : 'var(--accent)',
                      opacity: bar === 4 ? 0.45 : 1,
                      animationDelay: `${0.3 + bar * 0.06}s`,
                    }}
                  />
                ))}
              </div>
            )}

            {kpi.id === 'deals' && (
              <div className="mt-3.5 flex gap-1">
                {STAGE_SPLIT.map(segment => (
                  <div
                    key={segment.color}
                    className="h-[7px] rounded-full"
                    style={{ flex: segment.count, background: segment.color }}
                  />
                ))}
              </div>
            )}

            {(kpi.id === 'winRate' || kpi.id === 'goal') && (
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
