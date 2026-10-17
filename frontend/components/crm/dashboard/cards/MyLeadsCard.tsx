'use client';

import { Plus, Search, UserPlus } from 'lucide-react';
import Link from 'next/link';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import DashboardCardBody from '@/components/crm/dashboard/DashboardCardBody';
import DashboardListRow from '@/components/crm/dashboard/DashboardListRow';
import DashboardAvatar from '@/components/crm/dashboard/DashboardAvatar';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { useOwnedCardList } from '@/features/crm/dashboard';
import { listLeads, type Lead } from '@/features/crm/leads';

interface MyLeadsCardProps {
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

export default function MyLeadsCard({ isCustomizing, onRemove, dragHandleProps }: MyLeadsCardProps) {
  const { status, items, error, fetchedAt, search, setSearch } = useOwnedCardList((params) =>
    listLeads({ owner_id: params.ownerId, search: params.search || undefined, page_size: 5 }),
  );

  return (
    <DashboardCard
      icon={UserPlus}
      title="My Leads"
      fetchedAt={fetchedAt}
      footerHref="/leads"
      footerLabel="View Report"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
      headerActions={
        <Link
          href="/leads"
          aria-label="New lead"
          className="flex h-[26px] w-[26px] items-center justify-center rounded-lg transition hover:bg-[var(--surface-2)]"
          style={{ color: 'var(--muted)' }}
        >
          <Plus className="h-[14px] w-[14px]" />
        </Link>
      }
      toolbar={
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2"
            style={{ color: 'var(--faint)' }}
          />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search this list…"
            className="input w-full py-1.5 pl-8 text-[11.5px]"
          />
        </div>
      }
    >
      <DashboardCardBody<Lead>
        status={status}
        items={items}
        error={error}
        emptyIcon={UserPlus}
        emptyTitle={search ? 'No leads match your search' : 'No leads assigned to you'}
        emptyDescription={
          search
            ? 'Try a different name or company.'
            : "New leads will show up here as they're assigned."
        }
        renderRow={(lead) => (
          <DashboardListRow
            key={lead.id}
            href={`/leads/${lead.id}`}
            leading={<DashboardAvatar label={`${lead.first_name} ${lead.last_name}`} />}
            title={`${lead.first_name} ${lead.last_name}`}
            subtitle={lead.company ?? undefined}
            trailing={<StatusBadge label={humanize(lead.status)} variant={statusVariant(lead.status)} />}
          />
        )}
      />
    </DashboardCard>
  );
}
