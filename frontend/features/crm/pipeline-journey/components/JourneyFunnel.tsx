'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import JourneyStageRow from './JourneyStageRow';
import type { JourneyFunnelStat, JourneyStage, JourneyStageId } from '../types';

/* ============================================================
   JOURNEY FUNNEL
   The narrative centrepiece: five tapering stage rows with
   glowing particles drifting down them, closed off by a strip
   of whole-funnel figures. Clicking a row opens that stage in
   the deals drawer.
   ============================================================ */

interface JourneyFunnelProps {
  stages: JourneyStage[];
  stats: JourneyFunnelStat[];
  /** Total open opportunities, for the subheading */
  openDeals: number;
  /** Tooltips are suppressed while the drawer is covering the funnel */
  tooltipsEnabled: boolean;
  onOpenStage: (stage: JourneyStageId) => void;
}

/** Decorative deal-flow particles: left offset, size, colour, timing. */
const PARTICLES = [
  { left: '22%', size: 9, radius: '3px', color: '#a78bfa', duration: '5.2s', delay: '0s' },
  { left: '38%', size: 7, radius: '99px', color: '#c084fc', duration: '6.4s', delay: '0.8s' },
  { left: '50%', size: 10, radius: '3px', color: '#8b5cf6', duration: '4.6s', delay: '1.6s' },
  { left: '62%', size: 7, radius: '99px', color: '#38bdf8', duration: '7s', delay: '2.4s' },
  { left: '76%', size: 8, radius: '3px', color: '#a78bfa', duration: '5.8s', delay: '3.2s' },
  { left: '46%', size: 6, radius: '99px', color: '#34d399', duration: '6.8s', delay: '4s' },
];

export default function JourneyFunnel({
  stages,
  stats,
  openDeals,
  tooltipsEnabled,
  onOpenStage,
}: JourneyFunnelProps) {
  const [hovered, setHovered] = useState<JourneyStageId | null>(null);

  return (
    <div
      className="surface bd anim-fade-up relative overflow-hidden rounded-[28px] border px-7 pb-[34px] pt-[26px]"
      style={{ boxShadow: 'var(--shadow-card)', animationDelay: '0.1s' }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-10 left-1/2 -ml-[210px] h-[420px] w-[420px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(139, 92, 246, 0.14), transparent 68%)',
        }}
      />

      <div className="relative mb-[22px] flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="txt font-display text-[19px] font-extrabold tracking-[-0.02em]">
            Pipeline Journey
          </h2>
          <p className="txt-muted mt-[5px] text-[12.5px] font-medium">
            {openDeals} opportunities flowing toward revenue · hover a stage for detail, click to
            open
          </p>
        </div>
        <div className="surface-2 bd txt-muted flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11.5px] font-bold">
          <span
            className="anim-glow h-1.5 w-1.5 rounded-full bg-emerald-500"
            style={{ animationDuration: '2.4s' }}
          />
          Live
        </div>
      </div>

      <div className="relative flex flex-col items-center gap-[9px]">
        {/* Deal-flow particles drifting down behind the rows */}
        <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
          {PARTICLES.map(particle => (
            <div
              key={particle.left + particle.delay}
              className="anim-flow absolute top-0"
              style={{
                left: particle.left,
                width: particle.size,
                height: particle.size,
                borderRadius: particle.radius,
                background: particle.color,
                boxShadow: `0 0 12px ${particle.color}`,
                animationDuration: particle.duration,
                animationDelay: particle.delay,
              }}
            />
          ))}
        </div>

        {stages.map((stage, i) => (
          <JourneyStageRow
            key={stage.id}
            stage={stage}
            index={i}
            hovered={tooltipsEnabled && hovered === stage.id}
            onHoverChange={isHovered => setHovered(isHovered ? stage.id : null)}
            onOpen={() => onOpenStage(stage.id)}
          />
        ))}
      </div>

      {/* ── Whole-funnel figures ── */}
      <div className="bd mt-[30px] flex flex-wrap justify-between gap-4 border-t pt-[18px]">
        {stats.map(stat => (
          <div key={stat.id}>
            <div className="txt-faint text-[11px] font-bold uppercase tracking-[0.07em]">
              {stat.label}
            </div>
            <div
              className={cn(
                'font-display mt-1 text-[17px] font-extrabold tracking-[-0.02em]',
                stat.danger ? 'text-rose-600 dark:text-rose-400' : 'txt',
              )}
            >
              {stat.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
