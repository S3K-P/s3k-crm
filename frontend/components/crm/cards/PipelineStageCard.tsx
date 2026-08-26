import { cn } from '@/lib/utils';

/* ============================================================
   PIPELINE STAGE CARD
   Shows a single pipeline stage with deal count, value,
   and a visual progress bar. Reusable in Dashboard and
   Opportunities pipeline views.
   ============================================================ */

export interface PipelineStage {
  id: string;
  label: string;
  count: number;
  value: string;
  /** 0-100 percentage for the progress fill */
  percentage: number;
  /** Gradient classes for the progress bar */
  gradient?: string;
}

interface PipelineStageCardProps {
  stage: PipelineStage;
  className?: string;
}

export default function PipelineStageCard({ stage, className }: PipelineStageCardProps) {
  return (
    <div className={cn('surface bd rounded-xl border p-3.5', className)}>
      <div className="flex items-center justify-between">
        <span className="txt text-[13px] font-semibold">{stage.label}</span>
        <span
          className="rounded-full px-2 py-[2px] text-[10.5px] font-bold"
          style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
        >
          {stage.count} {stage.count === 1 ? 'deal' : 'deals'}
        </span>
      </div>

      <p className="txt font-display mt-1.5 text-[18px] font-bold leading-none tracking-tight">
        {stage.value}
      </p>

      {/* Progress bar */}
      <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full" style={{ background: 'var(--surface-2)' }}>
        <div
          className={cn(
            'h-full rounded-full bg-gradient-to-r transition-all duration-500',
            stage.gradient || 'from-violet-600 to-indigo-600',
          )}
          style={{ width: `${Math.min(stage.percentage, 100)}%` }}
        />
      </div>
    </div>
  );
}
