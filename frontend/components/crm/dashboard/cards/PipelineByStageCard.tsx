'use client';

import { Filter } from 'lucide-react';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import { formatMoney, type PipelineStage } from '@/features/crm/dashboard';

interface PipelineByStageCardProps {
  status: 'loading' | 'ready' | 'error';
  stages: PipelineStage[];
  total: string;
  fetchedAt: Date | null;
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

/** A light-to-solid ramp of the brand accent, one shade per stage. */
const FUNNEL_COLORS = ['#e4defa', '#c3b6ef', '#9f88e3', '#7c57d6', 'var(--accent)'];

export default function PipelineByStageCard({
  status,
  stages,
  total,
  fetchedAt,
  isCustomizing,
  onRemove,
  dragHandleProps,
}: PipelineByStageCardProps) {
  return (
    <DashboardCard
      icon={Filter}
      title="Pipeline by Stage"
      fetchedAt={fetchedAt}
      footerHref="/opportunities"
      footerLabel="View pipeline"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
      headerActions={
        status === 'ready' ? (
          <span className="font-display text-[13px] font-extrabold">{formatMoney(total)}</span>
        ) : undefined
      }
    >
      {status === 'loading' && (
        <div className="space-y-2.5 px-2 py-1" aria-busy="true">
          {Array.from({ length: 3 }, (_, i) => (
            <div
              key={i}
              className="h-[26px] animate-pulse rounded-[7px]"
              style={{ background: 'var(--surface-2)', width: `${100 - i * 18}%` }}
            />
          ))}
        </div>
      )}

      {status === 'error' && (
        <p className="txt-muted px-4 py-6 text-center text-[12px]">Could not load the pipeline.</p>
      )}

      {status === 'ready' && stages.length === 0 && (
        <p className="txt-muted px-4 py-6 text-center text-[12px]">
          Pipeline is empty. Deals you create will appear here by stage.
        </p>
      )}

      {status === 'ready' && stages.length > 0 && (
        <div className="space-y-[7px] px-2 py-1">
          {stages.map((stage, index) => (
            <div key={stage.id} className="flex items-center gap-3">
              <span
                className="w-[88px] shrink-0 truncate text-[11.5px] font-semibold"
                style={{ color: 'var(--muted)' }}
              >
                {stage.label}
              </span>
              <div
                className="h-[26px] flex-1 overflow-hidden rounded-[7px]"
                style={{ background: 'var(--surface-2)' }}
              >
                <div
                  className="flex h-full items-center whitespace-nowrap px-2.5 text-[11px] font-bold text-white"
                  style={{
                    width: `${Math.max(stage.percentage, 6)}%`,
                    background: FUNNEL_COLORS[index % FUNNEL_COLORS.length],
                  }}
                >
                  {stage.count} · {stage.value}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </DashboardCard>
  );
}
