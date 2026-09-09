'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { CalendarDays, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

import FilterSelect from '@/components/crm/forms/FilterSelect';
import { ListError } from '@/components/crm/shared/ListStates';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { statusVariant } from '@/components/crm/shared/statusVariants';
import { useAuth, usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  addDays,
  dayKey,
  entryHref,
  groupByDay,
  isSameDay,
  readCalendar,
  shift,
  startOfDay,
  windowFor,
  type CalendarEntry,
  type CalendarScale,
  type CalendarSource,
} from '@/features/crm/calendar';

/* ============================================================
   CALENDAR

   Meetings and tasks on one grid, read from
   `GET /api/v1/crm/calendar`.

   **Every boundary is computed in local time and sent as an
   instant.** The browser is the only party that knows what day
   it is for this user; the server compares instants and never
   guesses a zone. That is why `windowFor` builds `Date` objects
   from local midnights and the request carries `toISOString()`
   — and why there is no "date" parameter anywhere.

   Nothing is created here. A meeting is an activity and a task
   is a task; both are created where their rules live, and a
   calendar that could write would be a third place those rules
   had to be repeated. Clicking an entry opens it there.
   ============================================================ */

const SCALES: { value: CalendarScale; label: string }[] = [
  { value: 'month', label: 'Month' },
  { value: 'week', label: 'Week' },
  { value: 'day', label: 'Day' },
];

const SOURCE_OPTIONS = [
  { value: '', label: 'Meetings & tasks' },
  { value: 'MEETING', label: 'Meetings only' },
  { value: 'TASK', label: 'Tasks only' },
];

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function CalendarPage() {
  const { currentUser } = useAuth();
  const { can } = usePermissions();
  const maySeeAnything = can('activities', 'VIEW') || can('tasks', 'VIEW');

  const [scale, setScale] = useState<CalendarScale>('month');
  const [focus, setFocus] = useState<Date>(() => startOfDay(new Date()));
  const [source, setSource] = useState<string>('');
  const [mineOnly, setMineOnly] = useState(false);

  const [entries, setEntries] = useState<CalendarEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  const { start, end } = useMemo(() => windowFor(scale, focus), [scale, focus]);
  const ownerId = mineOnly ? (currentUser?.user.id ?? null) : null;

  // The fetch lives inside the effect and the reload is a state change, so
  // nothing calls setState synchronously in an effect body — the same shape
  // `useCollection` uses, for the same reason.
  useEffect(() => {
    if (!maySeeAnything) return;
    let cancelled = false;

    void (async () => {
      try {
        const body = await readCalendar({
          start,
          end,
          sources: source ? [source as CalendarSource] : undefined,
          ownerId,
        });
        if (!cancelled) {
          setEntries(body.entries);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setEntries([]);
          setError(describeApiError(caught, 'The calendar could not be loaded.'));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [maySeeAnything, start, end, source, ownerId, attempt]);

  const byDay = useMemo(() => groupByDay(entries ?? []), [entries]);

  if (!maySeeAnything) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="font-display txt text-[22px] font-extrabold">Calendar</h1>
        <p className="txt-muted mt-1 text-[13px]">
          You do not have permission to view meetings or tasks.
        </p>
      </div>
    );
  }

  const days: Date[] = [];
  for (let day = new Date(start); day < end; day = addDays(day, 1)) days.push(day);

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-teal-500 to-emerald-600">
            <CalendarDays className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Calendar</h1>
            <p className="txt-muted mt-0.5 text-[13px]">{describeWindow(scale, focus)}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-label="Previous"
            onClick={() => setFocus(shift(scale, focus, -1))}
            className="ctl rounded-lg p-2 transition hover:opacity-70"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setFocus(startOfDay(new Date()))}
            className="ctl bd rounded-lg border px-3 py-2 text-[13px] font-semibold transition hover:opacity-80"
          >
            Today
          </button>
          <button
            type="button"
            aria-label="Next"
            onClick={() => setFocus(shift(scale, focus, 1))}
            className="ctl rounded-lg p-2 transition hover:opacity-70"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <FilterSelect
          aria-label="Scale"
          value={scale}
          onChange={(event) => setScale(event.target.value as CalendarScale)}
          options={SCALES.map((item) => ({ value: item.value, label: item.label }))}
        />
        <FilterSelect
          aria-label="Show"
          value={source}
          onChange={(event) => setSource(event.target.value)}
          options={SOURCE_OPTIONS}
        />
        <label className="flex items-center gap-2 text-[13px]">
          <input
            type="checkbox"
            checked={mineOnly}
            onChange={(event) => setMineOnly(event.target.checked)}
            className="h-4 w-4"
          />
          <span className="txt font-medium">Only mine</span>
        </label>
        {entries === null && (
          <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Loading" />
        )}
      </div>

      {error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : scale === 'month' ? (
        <MonthGrid days={days} focus={focus} byDay={byDay} />
      ) : (
        <DayList days={days} byDay={byDay} />
      )}
    </div>
  );
}

function MonthGrid({
  days,
  focus,
  byDay,
}: {
  days: Date[];
  focus: Date;
  byDay: Map<string, CalendarEntry[]>;
}) {
  const today = new Date();
  return (
    <div className="surface bd overflow-x-auto rounded-2xl border">
      <div className="min-w-[720px]">
        <div className="bd grid grid-cols-7 border-b">
          {WEEKDAYS.map((label) => (
            <div key={label} className="txt-faint px-3 py-2 text-[11px] font-semibold uppercase">
              {label}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {days.map((day) => {
            const entries = byDay.get(dayKey(day)) ?? [];
            // Days from the neighbouring months are dimmed rather than left
            // blank: a grid with empty edge cells hides the entries actually
            // sitting in those weeks.
            const outside = day.getMonth() !== focus.getMonth();
            return (
              <div
                key={dayKey(day)}
                className="bd min-h-[104px] border-b border-r p-2 last:border-r-0"
                style={{ opacity: outside ? 0.45 : 1 }}
              >
                <p
                  className={
                    isSameDay(day, today)
                      ? 'mb-1 text-[12px] font-bold'
                      : 'txt-muted mb-1 text-[12px] font-semibold'
                  }
                  style={isSameDay(day, today) ? { color: 'var(--accent)' } : undefined}
                >
                  {day.getDate()}
                </p>
                <div className="space-y-1">
                  {entries.slice(0, 3).map((entry) => (
                    <EntryChip key={`${entry.source}-${entry.id}`} entry={entry} />
                  ))}
                  {entries.length > 3 && (
                    <p className="txt-faint text-[11px]">+{entries.length - 3} more</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DayList({ days, byDay }: { days: Date[]; byDay: Map<string, CalendarEntry[]> }) {
  return (
    <div className="space-y-4">
      {days.map((day) => {
        const entries = byDay.get(dayKey(day)) ?? [];
        return (
          <div key={dayKey(day)} className="surface bd rounded-2xl border p-4">
            <p className="txt mb-2 text-[13px] font-semibold">
              {day.toLocaleDateString(undefined, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })}
            </p>
            {entries.length === 0 ? (
              <p className="txt-faint text-[12px]">Nothing scheduled.</p>
            ) : (
              <div className="space-y-2">
                {entries.map((entry) => (
                  <EntryRow key={`${entry.source}-${entry.id}`} entry={entry} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function EntryChip({ entry }: { entry: CalendarEntry }) {
  return (
    <Link
      href={entryHref(entry)}
      className="ctl block truncate rounded px-1.5 py-0.5 text-[11px] transition hover:opacity-70"
      title={entry.title}
    >
      {!entry.all_day && <span className="txt-faint">{localTime(entry.start)} </span>}
      {entry.title}
    </Link>
  );
}

function EntryRow({ entry }: { entry: CalendarEntry }) {
  return (
    <Link
      href={entryHref(entry)}
      className="ctl flex flex-wrap items-center gap-3 rounded-lg px-3 py-2 transition hover:opacity-80"
    >
      <span className="txt-faint w-[70px] shrink-0 text-[12px] tabular-nums">
        {entry.all_day ? 'All day' : localTime(entry.start)}
      </span>
      <span className="txt min-w-0 flex-1 truncate text-[13px] font-medium">{entry.title}</span>
      <StatusBadge label={entry.source === 'MEETING' ? 'Meeting' : 'Task'} variant="neutral" />
      <StatusBadge label={entry.status} variant={statusVariant(entry.status)} />
    </Link>
  );
}

/** An instant rendered in the viewer's own zone — the only place a time is shown. */
function localTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function describeWindow(scale: CalendarScale, focus: Date): string {
  if (scale === 'month') {
    return focus.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  }
  if (scale === 'day') {
    return focus.toLocaleDateString(undefined, {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  }
  const { start, end } = windowFor('week', focus);
  const last = addDays(end, -1);
  return `${start.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} – ${last.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}`;
}
