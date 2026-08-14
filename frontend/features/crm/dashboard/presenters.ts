/**
 * Maps the dashboard API payload onto the presentational card contracts.
 *
 * Kept out of the page so the page stays a layout, and out of the cards so
 * they stay reusable. The rule everything here follows: **format, never
 * invent**. Where the API has nothing to say, these functions return
 * `undefined` and the card omits the line, rather than filling it with a
 * plausible-looking placeholder.
 */

import {
  CalendarDays,
  ClipboardList,
  Mail,
  NotebookPen,
  Phone,
  type LucideIcon,
} from 'lucide-react';

import type { ActivityEntry } from '@/components/crm/cards/ActivityItem';
import type { MeetingItem } from '@/components/crm/cards/MeetingCard';
import type { PipelineStage } from '@/components/crm/cards/PipelineStageCard';
import type { TaskItem, TaskPriority } from '@/components/crm/cards/TaskCard';
import type {
  DashboardActivity,
  DashboardActivityType,
  DashboardMeeting,
  DashboardTask,
  PipelineStageSummary,
} from '@/features/crm/dashboard/types';

/* ------------------------------------------------------------------
   Money
   ------------------------------------------------------------------ */

/**
 * Compact money for a headline figure, e.g. `$1.74M`.
 *
 * `currency` is `null` when the open deals span several currencies; the figure
 * is then shown bare, because no symbol would be true of all of it.
 */
export function formatMoney(value: string, currency: string | null): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return '—';

  const options: Intl.NumberFormatOptions = {
    notation: 'compact',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  };
  if (currency) {
    options.style = 'currency';
    options.currency = currency;
  }

  try {
    return new Intl.NumberFormat('en-US', options).format(amount);
  } catch {
    // An unknown ISO code must not blank the dashboard.
    return new Intl.NumberFormat('en-US', { notation: 'compact' }).format(amount);
  }
}

/* ------------------------------------------------------------------
   Time
   ------------------------------------------------------------------ */

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function timeOfDay(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

/** `10:00 AM` today, `Mon 10:00 AM` this week, `12 Aug` beyond it. */
export function formatWhen(iso: string, now: Date): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  if (isSameDay(date, now)) return timeOfDay(date);

  const days = Math.abs(date.getTime() - now.getTime()) / 86_400_000;
  if (days < 7) {
    return `${date.toLocaleDateString('en-US', { weekday: 'short' })} ${timeOfDay(date)}`;
  }
  return date.toLocaleDateString('en-US', { day: 'numeric', month: 'short' });
}

/** `25 min ago`, `3 hours ago`, `2 days ago`, then an absolute date. */
export function formatRelative(iso: string, now: Date): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';

  const seconds = Math.round((now.getTime() - date.getTime()) / 1000);
  if (seconds < 0) return formatWhen(iso, now);
  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`;

  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} ${days === 1 ? 'day' : 'days'} ago`;

  return date.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' });
}

/* ------------------------------------------------------------------
   Tasks
   ------------------------------------------------------------------ */

const TASK_PRIORITIES: Record<DashboardTask['priority'], TaskPriority> = {
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
};

export function toTaskItem(task: DashboardTask, now: Date): TaskItem {
  const due = task.due_date ? new Date(task.due_date) : null;
  const overdue = due !== null && due.getTime() < now.getTime() && !task.completed;

  return {
    id: task.id,
    title: task.title,
    description: task.description ?? undefined,
    priority: TASK_PRIORITIES[task.priority],
    // No due date is a real state; leave the line off rather than guess one.
    dueTime: due ? `${overdue ? 'Overdue · ' : ''}${formatWhen(task.due_date!, now)}` : undefined,
    completed: task.completed,
  };
}

/* ------------------------------------------------------------------
   Meetings
   ------------------------------------------------------------------ */

export function toMeetingItem(meeting: DashboardMeeting, now: Date): MeetingItem {
  const start = meeting.start_time ? formatWhen(meeting.start_time, now) : 'Time not set';
  const end =
    meeting.end_time && meeting.start_time
      ? timeOfDay(new Date(meeting.end_time))
      : null;

  return {
    id: meeting.id,
    title: meeting.title,
    time: end ? `${start} – ${end}` : start,
    // The API resolves the linked record's name, or nothing when the meeting
    // stands alone. There is no separate contact on the wire, so that row is
    // simply absent rather than filled with a plausible name.
    company: meeting.related_label ?? undefined,
    // Only future, non-cancelled meetings are returned, so this is accurate.
    status: 'upcoming',
  };
}

/* ------------------------------------------------------------------
   Pipeline
   ------------------------------------------------------------------ */

const STAGE_GRADIENTS = [
  'from-sky-500 to-blue-600',
  'from-violet-600 to-indigo-600',
  'from-amber-500 to-orange-500',
  'from-pink-500 to-rose-500',
  'from-emerald-500 to-green-600',
];

/**
 * Stage cards, with each bar drawn **relative to the largest stage**.
 *
 * The bar is a comparison between columns, not a completion percentage — the
 * data model has no notion of a target to be a percentage of.
 */
export function toPipelineStages(
  stages: PipelineStageSummary[],
  currency: string | null,
): PipelineStage[] {
  const values = stages.map((stage) => Number(stage.value)).map((n) => (Number.isFinite(n) ? n : 0));
  const largestValue = Math.max(0, ...values);
  const largestCount = Math.max(0, ...stages.map((stage) => stage.count));

  return stages.map((stage, index) => {
    const value = values[index] ?? 0;
    // Fall back to deal count when every stage is valued at zero, so a
    // populated-but-unvalued pipeline still reads as populated.
    const share =
      largestValue > 0
        ? value / largestValue
        : largestCount > 0
          ? stage.count / largestCount
          : 0;

    return {
      id: stage.stage_id,
      label: stage.name,
      count: stage.count,
      value: formatMoney(stage.value, currency),
      percentage: Math.round(share * 100),
      gradient: STAGE_GRADIENTS[index % STAGE_GRADIENTS.length],
    };
  });
}

/* ------------------------------------------------------------------
   Activities
   ------------------------------------------------------------------ */

const ACTIVITY_ICONS: Record<DashboardActivityType, { icon: LucideIcon; gradient: string }> = {
  CALL: { icon: Phone, gradient: 'from-emerald-500 to-green-600' },
  EMAIL: { icon: Mail, gradient: 'from-sky-500 to-blue-600' },
  MEETING: { icon: CalendarDays, gradient: 'from-violet-600 to-indigo-600' },
  NOTE: { icon: NotebookPen, gradient: 'from-amber-500 to-orange-500' },
  TASK: { icon: ClipboardList, gradient: 'from-pink-500 to-rose-500' },
};

export function toActivityEntry(activity: DashboardActivity, now: Date): ActivityEntry {
  const presentation = ACTIVITY_ICONS[activity.type] ?? ACTIVITY_ICONS.NOTE;

  return {
    id: activity.id,
    icon: presentation.icon,
    iconGradient: presentation.gradient,
    title: activity.subject,
    detail: activity.detail ?? undefined,
    timestamp: formatRelative(activity.occurred_at, now),
  };
}
