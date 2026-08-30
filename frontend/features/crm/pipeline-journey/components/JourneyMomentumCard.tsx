'use client';

import { cn } from '@/lib/utils';
import type { MomentumMetric } from '../types';

/* ============================================================
   JOURNEY MOMENTUM CARD
   Week-over-week movement — what was created, what advanced,
   what stalled, what closed — plus the deal-velocity trend.
   ============================================================ */

interface JourneyMomentumCardProps {
  metrics: MomentumMetric[];
}

/** Deal velocity over the last six weeks, oldest → newest. */
const VELOCITY_BARS = [
  { height: 44, opacity: 1, soft: true },
  { height: 62, opacity: 1, soft: true },
  { height: 50, opacity: 1, soft: true },
  { height: 78, opacity: 0.5, soft: false },
  { height: 66, opacity: 0.7, soft: false },
  { height: 100, opacity: 1, soft: false },
];

export default function JourneyMomentumCard({ metrics }: JourneyMomentumCardProps) {
  return (
    <div
      className="surface bd anim-fade-up rounded-[28px] border p-6"
      style={{ boxShadow: 'var(--shadow-card)', animationDelay: '0.22s' }}
    >
      <div className="flex items-baseline justify-between gap-2.5">
        <h2 className="txt font-display text-[17px] font-extrabold tracking-[-0.02em]">
          Pipeline Momentum
        </h2>
        <span className="txt-faint text-[11.5px] font-bold">Last 7 days</span>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        {metrics.map((metric, i) => (
          <div key={metric.id} className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="txt flex justify-between text-[12.5px] font-semibold">
                <span className="truncate">{metric.label}</span>
                <span className="font-extrabold tabular-nums">{metric.value}</span>
              </div>
              <div className="surface-2 mt-1.5 h-1.5 overflow-hidden rounded-full">
                <div
                  className={cn('anim-bar-grow h-full rounded-full bg-gradient-to-r', metric.gradient)}
                  style={{
                    width: `${metric.fillPct}%`,
                    animationDuration: '1.1s',
                    animationDelay: `${0.4 + i * 0.08}s`,
                  }}
                />
              </div>
            </div>
            <span
              className={cn(
                'w-11 text-right text-[11.5px] font-extrabold',
                metric.positive
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-400',
              )}
            >
              {metric.delta}
            </span>
          </div>
        ))}
      </div>

      <div className="bd mt-4 flex items-center justify-between gap-3 border-t pt-3.5">
        <div>
          <div className="txt-faint text-[11px] font-bold uppercase tracking-[0.07em]">
            Avg. deal velocity
          </div>
          <div className="txt font-display mt-[3px] text-[20px] font-extrabold tracking-[-0.03em]">
            26 days{' '}
            <span className="text-[12px] font-bold text-emerald-600 dark:text-emerald-400">
              ↓ 4 faster
            </span>
          </div>
        </div>
        <div aria-hidden className="flex h-[34px] items-end gap-[3px]">
          {VELOCITY_BARS.map((bar, i) => (
            <div
              key={i}
              className="w-[7px] rounded-[3px]"
              style={{
                height: `${bar.height}%`,
                background: bar.soft ? 'var(--accent-soft)' : 'var(--accent)',
                opacity: bar.opacity,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
