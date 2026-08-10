'use client';

import { cn } from '@/lib/utils';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';

/* ============================================================
   DATA TABLE
   Generic, sortable, responsive data table component.
   Reusable across Leads, Contacts, Accounts, Opportunities, etc.
   Uses existing design tokens throughout (surface, bd, txt, etc.)
   ============================================================ */

export type SortDirection = 'asc' | 'desc' | null;

export interface ColumnDef<T> {
  /** Unique key matching the data field */
  key: string;
  /** Column header label */
  label: string;
  /** Sortable? */
  sortable?: boolean;
  /** Custom render function */
  render?: (row: T) => React.ReactNode;
  /** Header alignment */
  align?: 'left' | 'center' | 'right';
  /** Min width hint for responsiveness */
  minWidth?: string;
  /** Hide on small screens */
  hideBelow?: 'sm' | 'md' | 'lg' | 'xl';
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  /** Key extractor for rows */
  rowKey: (row: T) => string;
  /** Current sort state */
  sortKey?: string | null;
  sortDirection?: SortDirection;
  onSort?: (key: string) => void;
  /** Row click handler */
  onRowClick?: (row: T) => void;
  /** Empty state message */
  emptyMessage?: string;
  /** Custom empty state rendered instead of emptyMessage */
  emptyState?: React.ReactNode;
  /** Keep the header visible while the body scrolls. Requires maxHeight. */
  stickyHeader?: boolean;
  /** CSS max-height for the scroll area, e.g. "560px" */
  maxHeight?: string;
  /** Render placeholder rows instead of data */
  loading?: boolean;
  /** Number of placeholder rows shown while loading */
  skeletonRows?: number;
  className?: string;
}

const hideClasses: Record<string, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
  xl: 'hidden xl:table-cell',
};

export default function DataTable<T>({
  columns,
  data,
  rowKey,
  sortKey,
  sortDirection,
  onSort,
  onRowClick,
  emptyMessage = 'No data found',
  emptyState,
  stickyHeader = false,
  maxHeight,
  loading = false,
  skeletonRows = 8,
  className,
}: DataTableProps<T>) {
  const renderSortIcon = (col: ColumnDef<T>) => {
    if (!col.sortable) return null;
    const isActive = sortKey === col.key;
    if (!isActive) return <ChevronsUpDown className="ml-1 inline h-3 w-3 opacity-40" />;
    return sortDirection === 'asc'
      ? <ChevronUp className="ml-1 inline h-3 w-3" style={{ color: 'var(--accent)' }} />
      : <ChevronDown className="ml-1 inline h-3 w-3" style={{ color: 'var(--accent)' }} />;
  };

  return (
    <div
      className={cn('w-full overflow-x-auto', maxHeight && 'overflow-y-auto', className)}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <table className="w-full min-w-[640px] border-collapse">
        {/* Head */}
        <thead className={cn(stickyHeader && 'sticky top-0 z-10')}>
          <tr className="bd border-b">
            {columns.map(col => (
              <th
                key={col.key}
                className={cn(
                  'px-4 py-3 text-left text-[11.5px] font-bold uppercase tracking-wider',
                  'txt-faint whitespace-nowrap',
                  col.align === 'center' && 'text-center',
                  col.align === 'right' && 'text-right',
                  col.sortable && 'cursor-pointer select-none hover:opacity-80',
                  col.hideBelow && hideClasses[col.hideBelow],
                  stickyHeader && 'bd border-b',
                )}
                style={{
                  minWidth: col.minWidth,
                  ...(stickyHeader ? { background: 'var(--surface)' } : null),
                }}
                onClick={() => col.sortable && onSort?.(col.key)}
              >
                {col.label}
                {renderSortIcon(col)}
              </th>
            ))}
          </tr>
        </thead>

        {/* Body */}
        <tbody>
          {loading ? (
            Array.from({ length: skeletonRows }).map((_, rowIndex) => (
              <tr key={`skeleton-${rowIndex}`} className="bd border-b last:border-b-0">
                {columns.map(col => (
                  <td
                    key={col.key}
                    className={cn('px-4 py-3', col.hideBelow && hideClasses[col.hideBelow])}
                  >
                    <div
                      className="h-3 rounded motion-safe:animate-pulse"
                      style={{ background: 'var(--border)', width: col.key === 'actions' ? '1.75rem' : '80%' }}
                    />
                  </td>
                ))}
              </tr>
            ))
          ) : data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className={cn(emptyState ? 'p-4' : 'txt-faint py-16 text-center text-sm')}
              >
                {emptyState ?? emptyMessage}
              </td>
            </tr>
          ) : (
            data.map(row => (
              <tr
                key={rowKey(row)}
                className={cn(
                  'bd border-b transition-colors last:border-b-0',
                  onRowClick && 'cursor-pointer',
                )}
                style={{ background: 'var(--surface)' }}
                onMouseEnter={e => { (e.currentTarget.style.background) = 'var(--surface-2)'; }}
                onMouseLeave={e => { (e.currentTarget.style.background) = 'var(--surface)'; }}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map(col => (
                  <td
                    key={col.key}
                    className={cn(
                      'px-4 py-3 text-[13px]',
                      col.align === 'center' && 'text-center',
                      col.align === 'right' && 'text-right',
                      col.hideBelow && hideClasses[col.hideBelow],
                    )}
                  >
                    {col.render
                      ? col.render(row)
                      : <span className="txt">{String((row as unknown as Record<string, unknown>)[col.key] ?? '')}</span>
                    }
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
