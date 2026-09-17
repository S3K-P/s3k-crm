import { X } from 'lucide-react';

import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import { cn } from '@/lib/utils';
import { SIGNAL_LABEL, type PriorityLevel, type RecordKind, type SignalFilter } from './nba-view';

/* ============================================================
   NBA QUEUE TOOLBAR

   Record type, text search, priority, and signal chips. Every
   filter narrows the queue the API already ranked — none of them
   re-orders it. Chip counts are for the current record type, so
   a chip never promises rows the list will not show.
   ============================================================ */

export type QueueScope = 'ALL' | RecordKind;

export interface QueueFilters {
  scope: QueueScope;
  search: string;
  level: PriorityLevel | '';
  signals: SignalFilter[];
}

export const EMPTY_FILTERS: QueueFilters = { scope: 'ALL', search: '', level: '', signals: [] };

const SCOPES: { value: QueueScope; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'OPPORTUNITY', label: 'Deals' },
  { value: 'LEAD', label: 'Leads' },
];

const LEVEL_OPTIONS = [
  { value: '', label: 'Any priority' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
];

export default function NbaQueueToolbar({
  filters,
  onChange,
  scopeCounts,
  signalCounts,
  availableSignals,
  shown,
  total,
}: {
  filters: QueueFilters;
  onChange: (next: QueueFilters) => void;
  scopeCounts: Record<QueueScope, number>;
  signalCounts: Record<SignalFilter, number>;
  availableSignals: SignalFilter[];
  shown: number;
  total: number;
}) {
  const active =
    filters.search.trim() !== '' || filters.level !== '' || filters.signals.length > 0 || filters.scope !== 'ALL';

  const toggleSignal = (signal: SignalFilter) =>
    onChange({
      ...filters,
      signals: filters.signals.includes(signal)
        ? filters.signals.filter((value) => value !== signal)
        : [...filters.signals, signal],
    });

  return (
    <div className="surface bd rounded-2xl border p-3 sm:p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="group" aria-label="Record type" className="ctl inline-flex w-full shrink-0 gap-1 p-1 sm:w-auto">
          {SCOPES.map((scope) => {
            const selected = filters.scope === scope.value;
            return (
              <button
                key={scope.value}
                type="button"
                aria-pressed={selected}
                onClick={() => onChange({ ...filters, scope: scope.value })}
                className={cn(
                  'flex-1 rounded-lg px-3.5 py-1.5 text-[12.5px] font-semibold transition sm:flex-none',
                  selected ? '' : 'txt-muted hover:text-[var(--text)]',
                )}
                style={selected ? { background: 'var(--accent-soft)', color: 'var(--accent)' } : undefined}
              >
                {scope.label} <span className="tabular-nums opacity-70">{scopeCounts[scope.value]}</span>
              </button>
            );
          })}
        </div>

        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
          <SearchInput
            value={filters.search}
            onChange={(event) => onChange({ ...filters, search: event.target.value })}
            placeholder="Search name, account, action…"
            aria-label="Search the queue"
            containerClassName="w-full min-w-0 sm:flex-1 lg:w-64 lg:flex-none"
          />
          <FilterSelect
            options={LEVEL_OPTIONS}
            value={filters.level}
            onChange={(event) => onChange({ ...filters, level: event.target.value as QueueFilters['level'] })}
            aria-label="Filter by priority"
          />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="txt-faint mr-1 text-[11px] font-bold uppercase tracking-wider">Signals</span>
        {availableSignals.map((signal) => {
          const selected = filters.signals.includes(signal);
          return (
            <button
              key={signal}
              type="button"
              aria-pressed={selected}
              onClick={() => toggleSignal(signal)}
              className={cn(
                'rounded-full border px-2.5 py-1 text-[12px] font-semibold transition',
                selected ? '' : 'bd txt-muted hover:text-[var(--text)]',
              )}
              style={
                selected
                  ? { background: 'var(--accent-soft)', color: 'var(--accent)', borderColor: 'var(--accent)' }
                  : undefined
              }
            >
              {SIGNAL_LABEL[signal]} <span className="tabular-nums opacity-70">{signalCounts[signal]}</span>
            </button>
          );
        })}

        <div className="ml-auto flex items-center gap-2 pl-2">
          <span className="txt-muted text-[12px] font-medium" aria-live="polite">
            {shown === total ? `${total} records` : `${shown} of ${total} records`}
          </span>
          {active && (
            <button
              type="button"
              onClick={() => onChange(EMPTY_FILTERS)}
              className="txt-muted inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] font-semibold transition hover:text-[var(--text)]"
            >
              <X className="h-3 w-3" aria-hidden="true" /> Clear
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
