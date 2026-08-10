import { cn } from '@/lib/utils';

/* ============================================================
   SCORE METER
   Accessible progress indicator used for AI confidence,
   relationship score, win probability and score factors.

   Status is never communicated by colour alone — the numeric
   value and a text classification are always rendered.
   ============================================================ */

export type MeterTone = 'accent' | 'positive' | 'caution' | 'negative';

interface ScoreMeterProps {
  /** 0–100 */
  value: number;
  label: string;
  /** Text classification shown next to the value, e.g. "High Confidence". */
  caption?: string;
  tone?: MeterTone;
  /** Compact variant for table cells and dense lists. */
  size?: 'sm' | 'md' | 'lg';
  /** Hide the label row — the label is still exposed to assistive tech. */
  hideLabel?: boolean;
  className?: string;
}

const toneBar: Record<MeterTone, string> = {
  accent: 'bg-[var(--accent)]',
  positive: 'bg-emerald-500',
  caution: 'bg-amber-500',
  negative: 'bg-rose-500',
};

const toneText: Record<MeterTone, string> = {
  accent: 'text-[var(--accent)]',
  positive: 'text-emerald-600 dark:text-emerald-400',
  caution: 'text-amber-600 dark:text-amber-400',
  negative: 'text-rose-600 dark:text-rose-400',
};

const barHeight: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'h-1',
  md: 'h-1.5',
  lg: 'h-2',
};

const valueSize: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'text-[12px]',
  md: 'text-[14px]',
  lg: 'text-[22px]',
};

/** Maps a 0–100 score onto a tone using the shared CRM thresholds. */
export function toneForScore(value: number): MeterTone {
  if (value >= 80) return 'positive';
  if (value >= 60) return 'accent';
  if (value >= 40) return 'caution';
  return 'negative';
}

export default function ScoreMeter({
  value,
  label,
  caption,
  tone = 'accent',
  size = 'md',
  hideLabel = false,
  className,
}: ScoreMeterProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <div className={cn('w-full', className)}>
      {!hideLabel && (
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <span className="txt-muted text-[11.5px] font-semibold">{label}</span>
          <span className={cn('font-display font-bold', valueSize[size], toneText[tone])}>
            {clamped}%
          </span>
        </div>
      )}

      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${clamped} percent${caption ? ` — ${caption}` : ''}`}
        className={cn('w-full overflow-hidden rounded-full', barHeight[size])}
        style={{ background: 'var(--border)' }}
      >
        <div
          className={cn('h-full rounded-full transition-[width] duration-500 ease-out', toneBar[tone])}
          style={{ width: `${clamped}%` }}
        />
      </div>

      {caption && (
        <p className={cn('mt-1 text-[11.5px] font-semibold', toneText[tone])}>{caption}</p>
      )}
    </div>
  );
}
