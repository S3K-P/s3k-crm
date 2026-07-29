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
    <div className={cn('w-full overflow-x-auto', className)}>
      <table className="w-full min-w-[640px] border-collapse">
        {/* Head */}
        <thead>
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
                )}
                style={{ minWidth: col.minWidth }}
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
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="txt-faint py-16 text-center text-sm">
                {emptyMessage}
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
