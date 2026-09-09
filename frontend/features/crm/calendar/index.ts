/**
 * Calendar — types and API access.
 *
 * Mirrors `backend/app/products/crm/calendar/schemas.py`.
 *
 * **The timezone contract is the whole of this module's difficulty**, so it is
 * stated once here and honoured by every function below:
 *
 * - The browser knows what day it is locally. The server does not, and must
 *   not guess.
 * - So a request carries two *instants* with offsets, produced by turning the
 *   user's local month into `Date` objects and calling `toISOString()`.
 * - The response carries instants in UTC, which `new Date(...)` renders back
 *   into local time for free.
 *
 * There is no "date" parameter anywhere, deliberately. A date has no instant
 * without a zone, and a server picking one would put a +14:00 user's Monday
 * meetings on Sunday — silently, in a way that looks like missing data.
 */

import { api } from '@/lib/api-client';
import type { CustomFieldEntityType } from '@/features/crm/custom-fields';

export type CalendarSource = 'MEETING' | 'TASK';

export const CALENDAR_SOURCES: CalendarSource[] = ['MEETING', 'TASK'];

export interface CalendarEntry {
  id: string;
  source: CalendarSource;
  title: string;
  /** ISO-8601 with an offset. */
  start: string;
  /** `null` for a task, and for a meeting with no end time. */
  end: string | null;
  /** A task occupies its due *day*, not an instant. */
  all_day: boolean;
  status: string;
  owner_id: string | null;
  related_entity_type: CustomFieldEntityType | null;
  related_entity_id: string | null;
  location: string | null;
  meeting_link: string | null;
}

export interface CalendarResponse {
  start: string;
  end: string;
  entries: CalendarEntry[];
}

export interface CalendarQuery {
  /** Inclusive. */
  start: Date;
  /** Exclusive. */
  end: Date;
  sources?: CalendarSource[];
  /** Narrows to one person. Cannot widen what the caller may see. */
  ownerId?: string | null;
}

/**
 * Read one window of the calendar.
 *
 * `toISOString()` always produces a `Z` instant, and `URLSearchParams` encodes
 * it — so the `+` of a positive offset can never reach the server as a space.
 * (The API repairs that case anyway; not producing it is better than relying on
 * the repair.)
 */
export function readCalendar(query: CalendarQuery) {
  const params = new URLSearchParams({
    start: query.start.toISOString(),
    end: query.end.toISOString(),
  });
  for (const source of query.sources ?? []) params.append('source', source);
  if (query.ownerId) params.set('owner_id', query.ownerId);
  return api.get<CalendarResponse>(`/crm/calendar?${params.toString()}`);
}

/* ------------------------------------------------------------------
   Local calendar arithmetic

   All of it in local time, because that is the only zone the grid is
   drawn in. `new Date(y, m, d)` builds a local midnight, which is
   exactly the boundary the user means by "the 1st".
   ------------------------------------------------------------------ */

export type CalendarScale = 'month' | 'week' | 'day';

/** The half-open window a scale covers, anchored on `focus`. */
export function windowFor(scale: CalendarScale, focus: Date): { start: Date; end: Date } {
  switch (scale) {
    case 'day': {
      const start = startOfDay(focus);
      return { start, end: addDays(start, 1) };
    }
    case 'week': {
      const start = startOfWeek(focus);
      return { start, end: addDays(start, 7) };
    }
    default: {
      // A month *grid* shows the trailing days of the previous month and the
      // leading days of the next, and those cells have to be populated or the
      // grid lies about the weeks at its edges.
      const start = startOfWeek(new Date(focus.getFullYear(), focus.getMonth(), 1));
      const end = addDays(startOfWeek(new Date(focus.getFullYear(), focus.getMonth() + 1, 1)), 7);
      return { start, end };
    }
  }
}

/** Move the focus by one unit of `scale`. */
export function shift(scale: CalendarScale, focus: Date, delta: number): Date {
  if (scale === 'month') {
    return new Date(focus.getFullYear(), focus.getMonth() + delta, 1);
  }
  return addDays(focus, delta * (scale === 'week' ? 7 : 1));
}

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** Monday-first, which is what the rest of the product's date handling assumes. */
export function startOfWeek(date: Date): Date {
  const start = startOfDay(date);
  // `getDay()` is 0 for Sunday; shifting by 6 puts Sunday at the end.
  const offset = (start.getDay() + 6) % 7;
  return addDays(start, -offset);
}

export function addDays(date: Date, days: number): Date {
  // Via the day-of-month rather than milliseconds: adding 24h across a
  // daylight-saving boundary lands an hour off and, twice a year, on the
  // wrong day.
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** Group entries by the local day they fall on, keyed by `YYYY-MM-DD`. */
export function groupByDay(entries: CalendarEntry[]): Map<string, CalendarEntry[]> {
  const grouped = new Map<string, CalendarEntry[]>();
  for (const entry of entries) {
    const key = dayKey(new Date(entry.start));
    const bucket = grouped.get(key);
    if (bucket) bucket.push(entry);
    else grouped.set(key, [entry]);
  }
  return grouped;
}

/**
 * A local day as `YYYY-MM-DD`.
 *
 * Built from the local getters rather than `toISOString().slice(0, 10)`, which
 * would give the *UTC* day — putting a 23:00 local entry on tomorrow's cell for
 * every user west of Greenwich.
 */
export function dayKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Where clicking an entry goes. */
export function entryHref(entry: CalendarEntry): string {
  return entry.source === 'MEETING' ? `/meetings/${entry.id}` : '/tasks';
}
