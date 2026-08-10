'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   TABLE PAGINATION
   Client-side pager for the AI module's data tables. Kept
   feature-local because the shared DataTable has no pagination
   contract of its own.
   ============================================================ */

interface TablePaginationProps {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  pageSizeOptions?: number[];
  className?: string;
}

export default function TablePagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 25, 50],
  className,
}: TablePaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const from = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, totalItems);

  // Compact window of page numbers around the current page.
  const windowStart = Math.max(1, Math.min(page - 1, totalPages - 2));
  const pages = Array.from({ length: Math.min(3, totalPages) }, (_, i) => windowStart + i).filter(
    candidate => candidate <= totalPages,
  );

  return (
    <div
      className={cn(
        'bd flex flex-col gap-3 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <p className="txt-muted text-[12.5px]" aria-live="polite">
          {totalItems === 0
            ? 'No recommendations'
            : `Showing ${from}–${to} of ${totalItems}`}
        </p>

        <label className="txt-faint flex items-center gap-1.5 text-[12px]">
          <span className="sr-only sm:not-sr-only">Rows</span>
          <select
            value={pageSize}
            onChange={event => onPageSizeChange(Number(event.target.value))}
            aria-label="Rows per page"
            className="ctl appearance-none px-2 py-1 text-[12px] font-medium outline-none focus:border-[var(--accent)]"
          >
            {pageSizeOptions.map(option => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        </label>
      </div>

      <nav className="flex items-center gap-1" aria-label="Pagination">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
          className="ctl txt-muted grid h-8 w-8 place-items-center rounded-lg transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>

        {pages.map(candidate => {
          const active = candidate === page;
          return (
            <button
              key={candidate}
              type="button"
              onClick={() => onPageChange(candidate)}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'grid h-8 min-w-8 place-items-center rounded-lg px-2 text-[12.5px] font-semibold transition',
                active ? 'text-white' : 'ctl txt-muted hover:opacity-80',
              )}
              style={active ? { background: 'var(--accent)' } : undefined}
            >
              {candidate}
            </button>
          );
        })}

        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Next page"
          className="ctl txt-muted grid h-8 w-8 place-items-center rounded-lg transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </nav>
    </div>
  );
}
