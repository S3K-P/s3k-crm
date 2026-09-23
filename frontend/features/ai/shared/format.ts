/* ============================================================
   AI MODULE FORMATTERS
   Small, module-scoped formatting helpers. Currency follows the
   CRM-wide display currency (INR, no decimals — see lib/currency).

   Every helper is deterministic and timezone-pinned so server and
   client render identical strings (no hydration mismatches).
   ============================================================ */

/** Fixed "today" for the demonstration dataset. Keeping this a constant
 *  (rather than `new Date()`) makes every derived label deterministic. */
export const DEMO_TODAY = '2026-08-07';

const DAY_MS = 86_400_000;

function toUtcDate(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`);
}

/** ₹12,50,000 / ₹1.25Cr — the CRM-wide INR formatters, re-exported so the
 *  AI module keeps its own import path. */
export { formatCompactCurrency, formatCurrency } from '@/lib/currency';

/** 12 Sep 2026 */
export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(toUtcDate(iso));
}

/** 12 Sep, 10:30 AM */
export function formatDateTime(iso: string, time: string): string {
  return `${new Intl.DateTimeFormat('en-US', {
    day: '2-digit',
    month: 'short',
    timeZone: 'UTC',
  }).format(toUtcDate(iso))}, ${time}`;
}

/** Whole days between the demo "today" and an ISO date. Negative = past. */
export function daysFromToday(iso: string, today: string = DEMO_TODAY): number {
  return Math.round((toUtcDate(iso).getTime() - toUtcDate(today).getTime()) / DAY_MS);
}

/** "Today" · "in 4 days" · "14 days ago" — derived from DEMO_TODAY, so stable. */
export function formatRelativeDay(iso: string, today: string = DEMO_TODAY): string {
  const delta = daysFromToday(iso, today);
  if (delta === 0) return 'Today';
  if (delta === 1) return 'Tomorrow';
  if (delta === -1) return 'Yesterday';
  return delta > 0 ? `in ${delta} days` : `${Math.abs(delta)} days ago`;
}

/** 82% */
export function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

/** Initials for avatar tiles — "Sarah Chen" → "SC" */
export function initials(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase() ?? '')
    .join('');
}
