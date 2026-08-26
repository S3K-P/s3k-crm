'use client';

import { formatMoney } from '@/features/crm/dashboard/presenters';
import type { JourneyGoal, JourneyHeroContent, JourneyTotals } from '../types';

/* ============================================================
   JOURNEY HERO
   The gradient banner: greeting, the animated open-pipeline
   figure, progress against the quarterly goal, and the AI
   "best next move" card that opens the closing-deals cut.
   ============================================================ */

interface JourneyHeroProps {
  content: JourneyHeroContent;
  totals: JourneyTotals;
  goal: JourneyGoal | null;
  /** 0 → 1 counter progress shared with the KPI row */
  progress: number;
  onOpenClosing: () => void;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function JourneyHero({
  content,
  totals,
  goal,
  progress,
  onOpenClosing,
}: JourneyHeroProps) {
  const pipelineText = formatMoney(String(totals.pipelineValue * progress), totals.currency);
  // No goal model in the CRM, so no percentage — see `use-journey-data.ts`.
  const goalText = totals.goalPct === null ? null : `${Math.round(totals.goalPct * progress)}%`;

  return (
    <section
      className="anim-fade-up relative overflow-hidden rounded-[28px] px-[34px] py-8 text-white"
      style={{
        background: 'linear-gradient(135deg, #2a1d4d 0%, #6d28d9 58%, #9333ea 100%)',
        boxShadow: '0 30px 60px -30px rgba(76, 29, 149, 0.65)',
      }}
    >
      {/* Ambient glows */}
      <div
        aria-hidden
        className="anim-glow pointer-events-none absolute -right-[70px] -top-[90px] h-[290px] w-[290px] rounded-full blur-[60px]"
        style={{ background: 'rgba(236, 72, 153, 0.4)' }}
      />
      <div
        aria-hidden
        className="anim-glow pointer-events-none absolute -bottom-[120px] left-[26%] h-[260px] w-[260px] rounded-full blur-[60px]"
        style={{ background: 'rgba(56, 189, 248, 0.32)', animationDelay: '1s', animationDuration: '9s' }}
      />

      <div className="relative flex flex-wrap items-end justify-between gap-7">
        {/* ── Left: greeting + headline figure + goal bar ── */}
        <div className="min-w-0 flex-[1_1_320px]">
          <div className="inline-flex items-center gap-[7px] rounded-full bg-white/[0.16] px-[11px] py-[5px] text-[11px] font-bold uppercase tracking-[0.1em] backdrop-blur-[8px]">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_0_3px_rgba(74,222,128,0.28)]" />
            Your business pulse
          </div>

          <h1 className="font-display mt-3.5 text-[34px] font-extrabold leading-[1.1] tracking-[-0.03em]">
            {getGreeting()} 👋
          </h1>
          <p className="mt-2 text-[15px] font-medium text-white/[0.78]">{content.periodLine}</p>

          <div className="mt-[26px] flex items-end gap-3.5">
            <div className="font-display text-[52px] font-black leading-none tracking-[-0.04em] tabular-nums">
              {pipelineText}
            </div>
            <div className="pb-[7px]">
              <div className="text-[12px] font-bold uppercase tracking-[0.08em] text-white/[0.62]">
                Open pipeline
              </div>
              <div className="mt-[3px] text-[12.5px] font-bold text-emerald-300">
                {content.pipelineDelta}
              </div>
            </div>
          </div>

          {/* The goal bar renders only when there is a target to measure
              against. With no revenue-goal model in the CRM there is nothing
              to divide by, so the whole block is omitted rather than drawn
              empty at 0% — an empty progress bar under "Quarterly goal" is a
              claim that the quarter is going badly. */}
          {goal !== null && goalText !== null && (
            <div className="mt-[18px] max-w-[460px]">
              <div className="mb-[7px] flex justify-between text-[12px] font-bold text-white/80">
                <span>Quarterly goal · {goal.target}</span>
                <span className="tabular-nums">{goalText}</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-white/[0.18] p-0.5">
                <div
                  className="anim-bar-grow h-2 rounded-full"
                  style={{
                    width: `${totals.goalPct}%`,
                    background: 'linear-gradient(90deg, #a78bfa, #f0abfc 60%, #7dd3fc)',
                    boxShadow: '0 0 18px rgba(240, 171, 252, 0.8)',
                    animationDelay: '0.25s',
                  }}
                />
              </div>
              <p className="mt-2.5 text-[12.5px] font-semibold text-white/[0.72]">
                {content.goalCaption}
              </p>
            </div>
          )}
        </div>

        {/* ── Right: next best move + mini stats ── */}
        <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-2.5">
          {/* "Best next move" was a recommendation, and nothing in the CRM
              makes recommendations. Rendering the card with empty copy would
              leave a blank panel and a nameless button, so it is omitted
              until something can fill it. */}
          {content.nextMove !== '' && (
            <div className="rounded-[20px] border border-white/[0.18] bg-white/[0.12] px-[18px] py-4 backdrop-blur-[14px]">
              <div className="text-[11.5px] font-bold uppercase tracking-[0.08em] text-white/70">
                Best next move
              </div>
              <p className="mt-[7px] text-[14px] font-semibold leading-[1.45]">
                {content.nextMove}
              </p>
              <button
                type="button"
                onClick={onOpenClosing}
                className="mt-3 rounded-[10px] bg-white px-3.5 py-2 text-[12.5px] font-bold text-violet-900 transition hover:opacity-90"
              >
                {content.nextMoveCta}
              </button>
            </div>
          )}

          <div className="flex gap-2.5">
            {content.tiles.map(tile => (
              <div
                key={tile.id}
                className="flex-1 rounded-2xl border border-white/[0.16] bg-white/10 px-3.5 py-3"
              >
                <div className="font-display text-[19px] font-extrabold tracking-[-0.02em]">
                  {tile.value}
                </div>
                <div className="mt-0.5 text-[11px] font-semibold text-white/[0.68]">
                  {tile.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
