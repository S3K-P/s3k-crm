'use client';

import type { JourneyGoal, JourneyTotals } from '../types';

/* ============================================================
   JOURNEY GOAL CARD
   Progress against the quarterly revenue goal as a radial dial,
   the four figures behind it, and the closing nudge.
   ============================================================ */

interface JourneyGoalCardProps {
  goal: JourneyGoal;
  totals: JourneyTotals;
  /** 0 → 1 counter progress shared with the hero */
  progress: number;
}

/** Radius of the dial; the dash array is its circumference. */
const RADIUS = 84;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function JourneyGoalCard({ goal, totals, progress }: JourneyGoalCardProps) {
  // The dial needs a target to be a proportion *of*. Without one there is no
  // honest arc to draw, so the card declines to render and the page shows
  // `JourneyUnavailable` in its place. This is a guard rather than a default
  // of 0: a dial sitting at 0% is a statement about the quarter.
  if (totals.goalPct === null) return null;
  const goalPct = totals.goalPct;

  const dashOffset = CIRCUMFERENCE * (1 - goalPct / 100);

  const stats = [
    { id: 'wonThisMonth', label: 'Won this month', value: goal.wonThisMonth },
    { id: 'expected', label: 'Expected', value: goal.expected },
    { id: 'gap', label: 'Gap to target', value: goal.gap, accent: true },
    { id: 'days', label: 'Days remaining', value: String(goal.daysRemaining) },
  ];

  return (
    <div
      className="surface bd anim-fade-up rounded-[28px] border p-[26px]"
      style={{ boxShadow: 'var(--shadow-card)', animationDelay: '0.16s' }}
    >
      <h2 className="txt font-display text-[19px] font-extrabold tracking-[-0.02em]">Your Goal</h2>
      <p className="txt-muted mt-[5px] text-[12.5px] font-medium">{goal.period} revenue goal</p>

      <div className="relative mx-auto mb-1.5 mt-5 grid h-[212px] w-[212px] place-items-center">
        <svg width="212" height="212" viewBox="0 0 212 212" className="-rotate-90">
          <circle
            cx="106"
            cy="106"
            r={RADIUS}
            fill="none"
            stroke="var(--surface-2)"
            strokeWidth="18"
          />
          <circle
            cx="106"
            cy="106"
            r={RADIUS}
            fill="none"
            stroke="url(#journeyGoalGradient)"
            strokeWidth="18"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={dashOffset}
            className="anim-radial"
            style={{ animationDelay: '0.35s' }}
          />
          <defs>
            <linearGradient id="journeyGoalGradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#6d28d9" />
              <stop offset="55%" stopColor="#a855f7" />
              <stop offset="100%" stopColor="#38bdf8" />
            </linearGradient>
          </defs>
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="txt font-display text-[40px] font-black leading-none tracking-[-0.04em] tabular-nums">
            {Math.round(goalPct * progress)}%
          </div>
          <div className="txt-muted mt-1.5 text-[12px] font-bold">complete</div>
          <div className="mt-2 text-[12.5px] font-bold" style={{ color: 'var(--accent)' }}>
            {goal.won} / {goal.target}
          </div>
        </div>
      </div>

      <div className="mt-3.5 grid grid-cols-2 gap-2.5">
        {stats.map(stat => (
          <div key={stat.id} className="surface-2 bd rounded-2xl border px-3.5 py-3">
            <div className="txt-faint text-[10.5px] font-bold uppercase tracking-[0.06em]">
              {stat.label}
            </div>
            <div
              className="font-display mt-1 text-[18px] font-extrabold tracking-[-0.02em]"
              style={{ color: stat.accent ? 'var(--accent)' : 'var(--text)' }}
            >
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      <div
        className="mt-3.5 rounded-[18px] border px-4 py-3.5"
        style={{
          background:
            'linear-gradient(135deg, rgba(109, 40, 217, 0.1), rgba(147, 51, 234, 0.06))',
          borderColor: 'var(--accent-soft)',
        }}
      >
        <p className="txt text-[13px] font-bold tracking-[-0.01em]">{goal.headline}</p>
        <p className="txt-muted mt-[5px] text-[12.5px] font-medium leading-[1.5]">
          {goal.supporting}
        </p>
      </div>
    </div>
  );
}
