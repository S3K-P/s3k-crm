'use client';

import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { JourneyStage, StageDetailLevel } from '../types';

/* ============================================================
   JOURNEY STAGE ROW
   One trapezoid in the funnel. `widthPct` sets how wide the row
   is and `taperPct` insets its bottom edge, so each row's bottom
   meets the next row's top and the five read as one funnel.

   As the rows narrow there is less room for text, so `detail`
   steps the content down: `full` keeps both metric captions,
   `compact` drops them, `minimal` folds conversion into a
   caption under the value.
   ============================================================ */

interface JourneyStageRowProps {
  stage: JourneyStage;
  /** Index in the funnel, used to stagger the entrance */
  index: number;
  hovered: boolean;
  onHoverChange: (hovered: boolean) => void;
  onOpen: () => void;
}

/** Horizontal breathing room shrinks as the trapezoid narrows. */
const PADDING_X: Record<StageDetailLevel, string> = {
  full: 'clamp(14px, 9%, 74px)',
  compact: 'clamp(12px, 8%, 56px)',
  minimal: 'clamp(12px, 8%, 46px)',
};

function movementLabel(movement: number): string {
  return `${movement > 0 ? '+' : '−'}${Math.abs(movement)}`;
}

function subLabel(stage: JourneyStage): string {
  const move = movementLabel(stage.movement);
  if (stage.isTerminal) return `${stage.count} deals · ${move}`;
  if (stage.detail === 'full') return `${stage.count} opportunities · ${move} this week`;
  return `${stage.count} opps · ${move}`;
}

export default function JourneyStageRow({
  stage,
  index,
  hovered,
  onHoverChange,
  onOpen,
}: JourneyStageRowProps) {
  const { detail, isTerminal } = stage;

  return (
    <div className="relative z-[1]" style={{ width: `${stage.widthPct}%` }}>
      <button
        type="button"
        onMouseEnter={() => onHoverChange(true)}
        onMouseLeave={() => onHoverChange(false)}
        onFocus={() => onHoverChange(true)}
        onBlur={() => onHoverChange(false)}
        onClick={onOpen}
        aria-label={`${stage.label} — ${stage.count} opportunities worth ${stage.value}. Open the filtered list.`}
        className="anim-stage-in block w-full cursor-pointer rounded-[2px] text-left outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent)] focus-visible:ring-offset-2"
        style={{ animationDelay: `${index * 0.1}s` }}
      >
        <div
          className={cn(
            'bg-gradient-to-br transition-[filter,transform] duration-[250ms] hover:scale-[1.015] hover:brightness-[1.14] hover:saturate-[1.1]',
            stage.gradient,
            isTerminal && 'rounded-b-[20px] shadow-[0_18px_40px_-20px_rgba(16,185,129,0.7)]',
          )}
          style={{
            padding: `18px ${PADDING_X[detail]}`,
            clipPath: isTerminal
              ? undefined
              : `polygon(0 0, 100% 0, ${100 - stage.taperPct}% 100%, ${stage.taperPct}% 100%)`,
          }}
        >
          <div className="flex items-center justify-between gap-4 text-white">
            {/* Stage identity */}
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-lg bg-white/[0.18] text-[11.5px] font-extrabold">
                {isTerminal ? <Check className="h-3.5 w-3.5" strokeWidth={2.4} /> : stage.position}
              </span>
              <div className="min-w-0">
                <div className="text-[15px] font-bold tracking-[-0.01em]">{stage.label}</div>
                <div className="truncate text-[11.5px] font-semibold text-white/70">
                  {subLabel(stage)}
                </div>
              </div>
            </div>

            {/* Metrics — how many fit depends on how far the funnel has narrowed */}
            {detail === 'minimal' ? (
              <div className="shrink-0 text-right">
                <div className="font-display text-[19px] font-extrabold tracking-[-0.02em]">
                  {stage.value}
                </div>
                <div
                  className="text-[10.5px] font-bold"
                  style={{ color: isTerminal ? 'rgba(255,255,255,0.75)' : stage.conversionColor }}
                >
                  {stage.minimalCaption}
                </div>
              </div>
            ) : (
              <div className="flex min-w-0 flex-[0_1_auto] items-center gap-[clamp(8px,3%,26px)]">
                <div className="text-right">
                  <div className="font-display text-[20px] font-extrabold tracking-[-0.02em]">
                    {stage.value}
                  </div>
                  {detail === 'full' && (
                    <div className="text-[10.5px] font-bold uppercase tracking-[0.07em] text-white/[0.62]">
                      Potential
                    </div>
                  )}
                </div>
                <div className={cn('text-right', detail === 'full' ? 'w-[74px]' : 'w-11')}>
                  <div
                    className="text-[15px] font-extrabold"
                    style={{ color: stage.conversionColor }}
                  >
                    {stage.conversion}%
                  </div>
                  {detail === 'full' && (
                    <div className="text-[10.5px] font-bold uppercase tracking-[0.07em] text-white/[0.62]">
                      Converts
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </button>

      {/* ── Hover / focus tooltip ── */}
      {hovered && (
        <div
          role="tooltip"
          className="anim-tip-in bd pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[250px] rounded-2xl border px-4 py-3.5 backdrop-blur-[18px]"
          style={{
            background: 'var(--glass)',
            borderColor: 'var(--glass-bd)',
            boxShadow: '0 24px 50px -20px rgba(30, 10, 60, 0.45)',
          }}
        >
          <div className="txt text-[13px] font-extrabold tracking-[-0.01em]">{stage.label}</div>
          <div className="mt-2.5 grid grid-cols-2 gap-2.5">
            <TooltipMetric label={stage.tooltipLabels.count} value={String(stage.count)} />
            <TooltipMetric label={stage.tooltipLabels.value} value={stage.value} />
            <TooltipMetric label={stage.tooltipLabels.conversion} value={`${stage.conversion}%`} />
            <TooltipMetric
              label="Movement"
              value={movementLabel(stage.movement)}
              tone={stage.movement >= 0 ? 'positive' : 'negative'}
            />
          </div>
          <div className="bd txt-muted mt-[11px] border-t pt-[9px] text-[11.5px] font-semibold">
            {stage.tooltipFootnote}
          </div>
        </div>
      )}
    </div>
  );
}

function TooltipMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'positive' | 'negative';
}) {
  return (
    <div>
      <div className="txt-faint text-[10.5px] font-bold uppercase tracking-[0.06em]">{label}</div>
      {/* `.txt` is authored after Tailwind's utilities, so it would win over a
          colour utility — only reach for it when the metric has no tone. */}
      <div
        className={cn(
          'text-[15px] font-extrabold',
          !tone && 'txt',
          tone === 'positive' && 'text-emerald-600 dark:text-emerald-400',
          tone === 'negative' && 'text-rose-600 dark:text-rose-400',
        )}
      >
        {value}
      </div>
    </div>
  );
}
