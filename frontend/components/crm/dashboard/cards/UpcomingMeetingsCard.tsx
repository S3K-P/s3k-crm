'use client';

import { CalendarDays, Plus } from 'lucide-react';
import Link from 'next/link';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import DashboardCardBody from '@/components/crm/dashboard/DashboardCardBody';
import DashboardListRow from '@/components/crm/dashboard/DashboardListRow';
import { formatWhen, type DashboardMeeting } from '@/features/crm/dashboard';

interface UpcomingMeetingsCardProps {
  status: 'loading' | 'ready' | 'error';
  meetings: DashboardMeeting[];
  fetchedAt: Date | null;
  now: Date;
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

export default function UpcomingMeetingsCard({
  status,
  meetings,
  fetchedAt,
  now,
  isCustomizing,
  onRemove,
  dragHandleProps,
}: UpcomingMeetingsCardProps) {
  return (
    <DashboardCard
      icon={CalendarDays}
      title="Upcoming Meetings"
      fetchedAt={fetchedAt}
      footerHref="/meetings"
      footerLabel="View all"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
      headerActions={
        <Link
          href="/meetings"
          aria-label="Schedule meeting"
          className="flex h-[26px] w-[26px] items-center justify-center rounded-lg transition hover:bg-[var(--surface-2)]"
          style={{ color: 'var(--muted)' }}
        >
          <Plus className="h-[14px] w-[14px]" />
        </Link>
      }
    >
      <DashboardCardBody<DashboardMeeting>
        status={status}
        items={meetings}
        emptyIcon={CalendarDays}
        emptyTitle="No meetings scheduled"
        emptyDescription="Meetings you schedule will show up here."
        renderRow={(meeting) => (
          <DashboardListRow
            key={meeting.id}
            title={meeting.title}
            subtitle={meeting.related_label ?? undefined}
            trailing={
              meeting.start_time ? (
                <span className="text-[11px] font-semibold" style={{ color: 'var(--muted)' }}>
                  {formatWhen(meeting.start_time, now)}
                </span>
              ) : undefined
            }
          />
        )}
      />
    </DashboardCard>
  );
}
