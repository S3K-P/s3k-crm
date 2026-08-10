'use client';

import { SearchX, Sparkles } from 'lucide-react';
import DataTable, { type ColumnDef, type SortDirection } from '@/components/crm/tables/DataTable';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import ScoreMeter from '@/components/crm/ai/shared/ScoreMeter';
import NbaRowActions, { type NbaAction } from './NbaRowActions';
import {
  PRIORITY_VARIANT,
  RISK_VARIANT,
  STATUS_VARIANT,
  confidenceLabel,
  confidenceTone,
} from './nba-helpers';
import { cn } from '@/lib/utils';
import { daysFromToday, formatCompactCurrency, formatDate } from '@/features/ai/shared/format';
import type { NbaRecord } from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA DATA TABLE
   Twelve prioritised columns; the remaining fields live in the
   details drawer rather than being crammed into the grid.
   Lower-value columns drop out progressively on narrow
   viewports and the table scrolls horizontally below that.
   ============================================================ */

interface NbaTableProps {
  records: NbaRecord[];
  loading: boolean;
  sortKey: string | null;
  sortDirection: SortDirection;
  onSort: (key: string) => void;
  onRowClick: (record: NbaRecord) => void;
  onAction: (action: NbaAction, record: NbaRecord) => void;
  openActionId: string | null;
  onOpenActionChange: (id: string | null) => void;
  regeneratingId: string | null;
  hasActiveFilters: boolean;
  onResetFilters: () => void;
}

export default function NbaTable({
  records,
  loading,
  sortKey,
  sortDirection,
  onSort,
  onRowClick,
  onAction,
  openActionId,
  onOpenActionChange,
  regeneratingId,
  hasActiveFilters,
  onResetFilters,
}: NbaTableProps) {
  const columns: ColumnDef<NbaRecord>[] = [
    {
      key: 'leadName',
      label: 'Lead / Company',
      sortable: true,
      minWidth: '190px',
      render: record => (
        <div className="min-w-0">
          <p className="txt truncate text-[13px] font-semibold">{record.leadName}</p>
          <p className="txt-muted truncate text-[12px]">{record.company}</p>
        </div>
      ),
    },
    {
      key: 'opportunity',
      label: 'Opportunity',
      sortable: true,
      minWidth: '200px',
      hideBelow: 'lg',
      render: record => (
        <div className="min-w-0">
          <p className="txt truncate text-[12.5px] font-medium" title={record.opportunity}>
            {record.opportunity}
          </p>
          <p className="txt-faint text-[11.5px]">{record.winProbability}% win probability</p>
        </div>
      ),
    },
    {
      key: 'stage',
      label: 'Stage',
      sortable: true,
      hideBelow: 'xl',
      render: record => <StatusBadge label={record.stage} variant="accent" />,
    },
    {
      key: 'assignedTo',
      label: 'Assigned To',
      sortable: true,
      hideBelow: 'xl',
      render: record => (
        <span className="txt-muted whitespace-nowrap text-[12.5px] font-medium">{record.assignedTo}</span>
      ),
    },
    {
      key: 'priority',
      label: 'Priority',
      sortable: true,
      render: record => <StatusBadge label={record.priority} variant={PRIORITY_VARIANT[record.priority]} />,
    },
    {
      key: 'recommendation',
      label: 'AI Recommendation',
      minWidth: '260px',
      render: record => (
        <div className="min-w-0 max-w-[320px]">
          <p className="txt text-[12.5px] font-medium leading-snug" title={record.recommendation}>
            {record.recommendation}
          </p>
          <p className="txt-faint mt-0.5 line-clamp-1 text-[11.5px]" title={record.reason}>
            {record.reason}
          </p>
        </div>
      ),
    },
    {
      key: 'confidence',
      label: 'Confidence',
      sortable: true,
      minWidth: '110px',
      render: record => (
        <div className="w-[92px]">
          <ScoreMeter
            value={record.confidence}
            label={`AI confidence for ${record.leadName}`}
            tone={confidenceTone(record.confidence)}
            size="sm"
            hideLabel
          />
          <p className="txt-muted mt-1 text-[11.5px] font-bold" title={confidenceLabel(record.confidence)}>
            {record.confidence}%
          </p>
        </div>
      ),
    },
    {
      key: 'dealRisk',
      label: 'Deal Risk',
      sortable: true,
      hideBelow: 'lg',
      render: record => (
        <span title={record.aiNotes}>
          <StatusBadge label={record.dealRisk} variant={RISK_VARIANT[record.dealRisk]} />
        </span>
      ),
    },
    {
      key: 'expectedRevenue',
      label: 'Revenue',
      sortable: true,
      align: 'right',
      hideBelow: 'md',
      render: record => (
        <span className="font-display txt whitespace-nowrap text-[13px] font-bold">
          {formatCompactCurrency(record.expectedRevenue)}
        </span>
      ),
    },
    {
      key: 'nextFollowUp',
      label: 'Next Follow-up',
      sortable: true,
      hideBelow: 'lg',
      render: record => {
        const delta = daysFromToday(record.nextFollowUp);
        const overdue = delta < 0;
        const today = delta === 0;
        return (
          <div className="whitespace-nowrap">
            <p className="txt-muted text-[12.5px]">{formatDate(record.nextFollowUp)}</p>
            <p
              className={cn(
                'text-[11px] font-semibold',
                overdue && 'text-rose-600 dark:text-rose-400',
                today && 'text-amber-600 dark:text-amber-400',
                !overdue && !today && 'txt-faint',
              )}
            >
              {overdue
                ? `${Math.abs(delta)} day${Math.abs(delta) === 1 ? '' : 's'} overdue`
                : today
                  ? 'Due today'
                  : `in ${delta} day${delta === 1 ? '' : 's'}`}
            </p>
          </div>
        );
      },
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: record => <StatusBadge label={record.status} variant={STATUS_VARIANT[record.status]} />,
    },
    {
      key: 'actions',
      label: '',
      align: 'right',
      render: record => (
        <NbaRowActions
          record={record}
          open={openActionId === record.id}
          onOpenChange={open => onOpenActionChange(open ? record.id : null)}
          onAction={onAction}
          regenerating={regeneratingId === record.id}
        />
      ),
    },
  ];

  return (
    <DataTable<NbaRecord>
      columns={columns}
      data={records}
      loading={loading}
      skeletonRows={10}
      rowKey={record => record.id}
      sortKey={sortKey}
      sortDirection={sortDirection}
      onSort={onSort}
      onRowClick={onRowClick}
      stickyHeader
      maxHeight="620px"
      className="min-w-full"
      emptyState={
        hasActiveFilters ? (
          <AiEmptyState
            icon={SearchX}
            title="No recommendations match these filters"
            description="Try widening the date range or clearing a filter to see more of the working set."
            action={
              <button
                type="button"
                onClick={onResetFilters}
                className="rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
                style={{ background: 'var(--accent)' }}
              >
                Reset filters
              </button>
            }
          />
        ) : (
          <AiEmptyState
            icon={Sparkles}
            title="No recommendations available"
            description="There is nothing in the current working set. New recommendations appear as CRM activity is recorded."
          />
        )
      }
    />
  );
}
