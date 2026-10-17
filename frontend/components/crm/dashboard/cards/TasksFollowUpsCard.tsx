'use client';

import { Circle, ClipboardList, Plus } from 'lucide-react';
import Link from 'next/link';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';
import DashboardCardBody from '@/components/crm/dashboard/DashboardCardBody';
import DashboardListRow from '@/components/crm/dashboard/DashboardListRow';
import StatusBadge, { type BadgeVariant } from '@/components/crm/shared/StatusBadge';
import { formatWhen, type DashboardTask } from '@/features/crm/dashboard';

interface TasksFollowUpsCardProps {
  status: 'loading' | 'ready' | 'error';
  tasks: DashboardTask[];
  fetchedAt: Date | null;
  now: Date;
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

function dueBadge(task: DashboardTask, now: Date): { label: string; variant: BadgeVariant } | null {
  if (!task.due_date) return null;
  const due = new Date(task.due_date);
  if (Number.isNaN(due.getTime())) return null;
  const overdue = due.getTime() < now.getTime();
  return { label: formatWhen(task.due_date, now), variant: overdue ? 'danger' : 'warning' };
}

export default function TasksFollowUpsCard({
  status,
  tasks,
  fetchedAt,
  now,
  isCustomizing,
  onRemove,
  dragHandleProps,
}: TasksFollowUpsCardProps) {
  return (
    <DashboardCard
      icon={ClipboardList}
      title="Tasks & Follow-ups"
      fetchedAt={fetchedAt}
      footerHref="/tasks"
      footerLabel="View all"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
      headerActions={
        <Link
          href="/tasks"
          aria-label="New task"
          className="flex h-[26px] w-[26px] items-center justify-center rounded-lg transition hover:bg-[var(--surface-2)]"
          style={{ color: 'var(--muted)' }}
        >
          <Plus className="h-[14px] w-[14px]" />
        </Link>
      }
    >
      <DashboardCardBody<DashboardTask>
        status={status}
        items={tasks}
        emptyIcon={ClipboardList}
        emptyTitle="You're all caught up"
        emptyDescription="No tasks due today."
        renderRow={(task) => {
          const badge = dueBadge(task, now);
          return (
            <DashboardListRow
              key={task.id}
              leading={<Circle className="mt-0.5 h-[15px] w-[15px]" style={{ color: 'var(--faint)' }} />}
              title={task.title}
              subtitle={task.description ?? undefined}
              trailing={badge ? <StatusBadge label={badge.label} variant={badge.variant} /> : undefined}
            />
          );
        }}
      />
    </DashboardCard>
  );
}
