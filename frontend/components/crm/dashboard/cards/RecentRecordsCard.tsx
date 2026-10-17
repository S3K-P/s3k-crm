'use client';

import { BarChart3 } from 'lucide-react';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import DashboardCardBody from '@/components/crm/dashboard/DashboardCardBody';
import DashboardListRow from '@/components/crm/dashboard/DashboardListRow';
import DashboardAvatar from '@/components/crm/dashboard/DashboardAvatar';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { formatRelative, useRecentRecords, type RecentRecordEntry } from '@/features/crm/dashboard';

interface RecentRecordsCardProps {
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

const RECORD_LABEL: Record<RecentRecordEntry['type'], string> = {
  LEAD: 'Lead',
  CONTACT: 'Contact',
  OPPORTUNITY: 'Deal',
};

const RECORD_HREF: Record<RecentRecordEntry['type'], string> = {
  LEAD: '/leads',
  CONTACT: '/contacts',
  OPPORTUNITY: '/opportunities',
};

export default function RecentRecordsCard({ isCustomizing, onRemove, dragHandleProps }: RecentRecordsCardProps) {
  const { status, items, error, fetchedAt } = useRecentRecords();
  const now = fetchedAt ?? new Date();

  return (
    <DashboardCard
      icon={BarChart3}
      title="Recent Records"
      fetchedAt={fetchedAt}
      footerHref="/leads"
      footerLabel="View All"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
    >
      <DashboardCardBody<RecentRecordEntry>
        status={status}
        items={items}
        error={error}
        emptyIcon={BarChart3}
        emptyTitle="Nothing recent"
        emptyDescription="Records you view or edit will show up here."
        renderRow={(record) => (
          <DashboardListRow
            key={`${record.type}-${record.id}`}
            href={`${RECORD_HREF[record.type]}/${record.id}`}
            leading={<DashboardAvatar label={record.label} variant="tile" />}
            title={
              <>
                {record.label}{' '}
                <StatusBadge label={RECORD_LABEL[record.type]} variant="accent" className="ml-1" />
              </>
            }
            subtitle={`${record.updated_at !== record.created_at ? 'updated' : 'added'} ${formatRelative(record.touched_at, now)}`}
          />
        )}
      />
    </DashboardCard>
  );
}
