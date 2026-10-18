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
import type {
  DashboardActivity,
  DashboardActivityType,
  PipelineStageSummary,
} from '@/features/crm/dashboard/types';
import { formatCompactCurrency } from '@/lib/currency';

/** One open pipeline stage, shaped for the funnel bar it renders as. */
export interface PipelineStage {
  id: string;
  label: string;
  count: number;
  value: string;
  /** 0-100, relative to the largest stage — a comparison, not a completion percentage. */
  percentage: number;
}

/* ------------------------------------------------------------------
   Money
   ------------------------------------------------------------------ */

/**
 * Compact money for a headline figure, e.g. `₹1.26Cr` or `₹4.5L`.
 *
 * Always in the CRM's display currency (see `lib/currency`), whatever code
 * an individual record carries — amounts are shown as stored, never converted.
 */
export function formatMoney(value: string | number): string {
  return formatCompactCurrency(value);
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
   Pipeline
   ------------------------------------------------------------------ */

/**
 * Stage cards, with each bar drawn **relative to the largest stage**.
 *
 * The bar is a comparison between columns, not a completion percentage — the
 * data model has no notion of a target to be a percentage of.
 */
export function toPipelineStages(
  stages: PipelineStageSummary[],
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
      value: formatMoney(stage.value),
      percentage: Math.round(share * 100),
    };
  });
}

/* ------------------------------------------------------------------
   Activities
   ------------------------------------------------------------------ */

const ACTIVITY_ICONS: Record<DashboardActivityType, { icon: LucideIcon; gradient: string }> = {
  CALL: { icon: Phone, gradient: 'from-emerald-500 to-green-600' },
  EMAIL: { icon: Mail, gradient: 'from-sky-500 to-blue-600' },
  MEETING: { icon: CalendarDays, gradient: 'from-accent to-accent-2' },
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
