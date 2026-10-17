'use client';

import { useEffect, useState } from 'react';
import { Plus, Target } from 'lucide-react';
import Link from 'next/link';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import DashboardCardBody from '@/components/crm/dashboard/DashboardCardBody';
import DashboardListRow from '@/components/crm/dashboard/DashboardListRow';
import { formatMoney, useOwnedCardList } from '@/features/crm/dashboard';
import { listOpportunities, listStages, type Opportunity } from '@/features/crm/opportunities';

interface MyDealsCardProps {
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

function formatCloseDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('en-US', { day: 'numeric', month: 'short' });
}

export default function MyDealsCard({ isCustomizing, onRemove, dragHandleProps }: MyDealsCardProps) {
  const { status, items, error, fetchedAt } = useOwnedCardList((params) =>
    listOpportunities({ owner_id: params.ownerId, search: params.search || undefined, is_open: true, page_size: 5 }),
  );

  // Stage names rarely change; one fetch for the card, not per row.
  const [stageNames, setStageNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    void listStages().then((stages) => {
      if (!cancelled) {
        setStageNames(Object.fromEntries(stages.map((stage) => [stage.id, stage.name])));
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <DashboardCard
      icon={Target}
      title="My Open Deals"
      fetchedAt={fetchedAt}
      footerHref="/opportunities"
      footerLabel="View Report"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
      headerActions={
        <Link
          href="/opportunities"
          aria-label="New deal"
          className="flex h-[26px] w-[26px] items-center justify-center rounded-lg transition hover:bg-[var(--surface-2)]"
          style={{ color: 'var(--muted)' }}
        >
          <Plus className="h-[14px] w-[14px]" />
        </Link>
      }
    >
      <DashboardCardBody<Opportunity>
        status={status}
        items={items}
        error={error}
        emptyIcon={Target}
        emptyTitle="No open deals"
        emptyDescription="Create an opportunity to start tracking it here."
        renderRow={(deal) => {
          const closeDate = formatCloseDate(deal.expected_close_date);
          const stage = stageNames[deal.stage_id];
          const subtitle = [stage, closeDate ? `closes ${closeDate}` : null].filter(Boolean).join(' · ');
          return (
            <DashboardListRow
              key={deal.id}
              href={`/opportunities/${deal.id}`}
              title={deal.name}
              subtitle={subtitle || undefined}
              trailing={
                <span className="font-display text-[13px] font-extrabold">
                  {formatMoney(deal.deal_value ?? '0')}
                </span>
              }
            />
          );
        }}
      />
    </DashboardCard>
  );
}
