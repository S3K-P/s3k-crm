'use client';

import { Clock } from 'lucide-react';
import Link from 'next/link';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import ActivityItem from '@/components/crm/cards/ActivityItem';
import { toActivityEntry, type DashboardActivity } from '@/features/crm/dashboard';

interface ActivityTimelineCardProps {
  status: 'loading' | 'ready' | 'error';
  activities: DashboardActivity[];
  fetchedAt: Date | null;
  now: Date;
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

export default function ActivityTimelineCard({
  status,
  activities,
  fetchedAt,
  now,
  isCustomizing,
  onRemove,
  dragHandleProps,
}: ActivityTimelineCardProps) {
  return (
    <DashboardCard
      icon={Clock}
      title="Activity Timeline"
      fetchedAt={fetchedAt}
      wide
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
      headerActions={
        <Link
          href="/meetings"
          className="flex items-center gap-1 text-[12.5px] font-semibold hover:opacity-80"
          style={{ color: 'var(--accent)' }}
        >
          All activities →
        </Link>
      }
    >
      {status === 'loading' && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3.5 px-2 py-1" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="h-8 animate-pulse rounded-lg" style={{ background: 'var(--surface-2)' }} />
          ))}
        </div>
      )}

      {status === 'error' && (
        <p className="txt-muted px-4 py-6 text-center text-[12px]">Could not load recent activity.</p>
      )}

      {status === 'ready' && activities.length === 0 && (
        <p className="txt-muted px-4 py-6 text-center text-[12px]">
          No recent activity. Calls, emails and notes you log will appear here.
        </p>
      )}

      {status === 'ready' && activities.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-x-3.5 gap-y-2 px-2 py-1">
          {activities.map((activity) => (
            <ActivityItem key={activity.id} activity={toActivityEntry(activity, now)} showConnector={false} />
          ))}
        </div>
      )}
    </DashboardCard>
  );
}
