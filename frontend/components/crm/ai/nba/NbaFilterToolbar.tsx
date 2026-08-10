'use client';

import { RotateCcw } from 'lucide-react';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import {
  CONFIDENCE_OPTIONS,
  FOLLOW_UP_OPTIONS,
  PRIORITY_OPTIONS,
  STAGE_OPTIONS,
  STATUS_OPTIONS,
  type NbaFilters,
} from '@/features/ai/next-best-action/filters';

/* ============================================================
   NBA FILTER TOOLBAR
   Reuses the CRM's existing SearchInput and FilterSelect so the
   controls match every other list page. Wraps onto multiple
   rows on smaller viewports rather than scrolling sideways.
   ============================================================ */

interface Option {
  value: string;
  label: string;
}

interface NbaFilterToolbarProps {
  filters: NbaFilters;
  onChange: <K extends keyof NbaFilters>(key: K, value: NbaFilters[K]) => void;
  onReset: () => void;
  companyOptions: Option[];
  salespersonOptions: Option[];
  activeFilterCount: number;
  resultCount: number;
  totalCount: number;
}

export default function NbaFilterToolbar({
  filters,
  onChange,
  onReset,
  companyOptions,
  salespersonOptions,
  activeFilterCount,
  resultCount,
  totalCount,
}: NbaFilterToolbarProps) {
  return (
    <div className="surface bd rounded-2xl border p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <SearchInput
          value={filters.search}
          onChange={event => onChange('search', event.target.value)}
          placeholder="Search lead, company, opportunity, owner or recommendation..."
          aria-label="Search recommendations"
          containerClassName="min-w-0 flex-1 lg:max-w-sm"
        />

        <div className="flex flex-wrap gap-2">
          <FilterSelect
            options={companyOptions}
            value={filters.company}
            onChange={event => onChange('company', event.target.value)}
            aria-label="Filter by company"
          />
          <FilterSelect
            options={salespersonOptions}
            value={filters.salesperson}
            onChange={event => onChange('salesperson', event.target.value)}
            aria-label="Filter by salesperson"
          />
          <FilterSelect
            options={PRIORITY_OPTIONS}
            value={filters.priority}
            onChange={event => onChange('priority', event.target.value)}
            aria-label="Filter by priority"
          />
          <FilterSelect
            options={STATUS_OPTIONS}
            value={filters.status}
            onChange={event => onChange('status', event.target.value)}
            aria-label="Filter by status"
          />
          <FilterSelect
            options={CONFIDENCE_OPTIONS}
            value={filters.confidence}
            onChange={event => onChange('confidence', event.target.value)}
            aria-label="Filter by AI confidence"
          />
          <FilterSelect
            options={STAGE_OPTIONS}
            value={filters.stage}
            onChange={event => onChange('stage', event.target.value)}
            aria-label="Filter by deal stage"
          />
          <FilterSelect
            options={FOLLOW_UP_OPTIONS}
            value={filters.followUp}
            onChange={event => onChange('followUp', event.target.value)}
            aria-label="Filter by follow-up date"
          />
        </div>
      </div>

      <div className="bd mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <p className="txt-muted text-[12.5px] font-medium" aria-live="polite">
          {resultCount === totalCount
            ? `${totalCount} recommendations`
            : `${resultCount} of ${totalCount} recommendations`}
          {activeFilterCount > 0 && (
            <span className="txt-faint"> · {activeFilterCount} filter{activeFilterCount > 1 ? 's' : ''} active</span>
          )}
        </p>

        <button
          type="button"
          onClick={onReset}
          disabled={activeFilterCount === 0}
          className="ctl txt-muted flex items-center gap-1.5 px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          Reset filters
        </button>
      </div>
    </div>
  );
}
