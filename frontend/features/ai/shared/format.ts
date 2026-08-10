/* ============================================================
   AI MODULE FORMATTERS
   Small, module-scoped formatting helpers. Currency follows the
   existing CRM convention (USD, no decimals — see Opportunities).

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

/** $1,250,000 */
export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

/** $1.25M / $480K — for KPI tiles and chart axes */
export function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    const millions = value / 1_000_000;
    return `$${millions.toFixed(millions >= 10 ? 1 : 2).replace(/\.0+$/, '')}M`;
  }
  if (Math.abs(value) >= 1_000) return `$${Math.round(value / 1_000)}K`;
  return `$${value}`;
}

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
