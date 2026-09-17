'use client';

import { useState } from 'react';
import { Check, ChevronDown, ChevronUp, ChevronsUpDown, Loader2, X } from 'lucide-react';

import { cn } from '@/lib/utils';

/* ============================================================
   DATA TABLE
   Generic, sortable, responsive data table component.
   Reusable across Leads, Contacts, Accounts, Opportunities, etc.
   Uses existing design tokens throughout (surface, bd, txt, etc.)

   Checkpoint 4 adds two opt-in capabilities, both off unless a
   caller passes the props they need:

   - **Inline editing.** A column declares `editable`/`editType`
     and the table owns the click-to-edit/save/cancel state
     itself, calling back into `onCellEdit` to persist — so every
     page gets the same interaction (Enter/blur saves, Escape
     cancels, a failed save shows its message on the cell and
     keeps the edit open) instead of five copies of it.
   - **Row selection.** `selectable` renders the checkbox column
     every list page was hand-rolling identically (leads,
     accounts, contacts each pasted the same synthetic column) —
     centralised here once, for bulk actions to build on.
   ============================================================ */

export type SortDirection = 'asc' | 'desc' | null;

export type EditType = 'text' | 'number' | 'email' | 'tel' | 'date' | 'select';

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
  /** Whether this cell may be edited in place, per row (Checkpoint 4). */
  editable?: (row: T) => boolean;
  /** Which control to show while editing. Defaults to `text`. */
  editType?: EditType;
  /** Options for `editType: 'select'`. */
  editOptions?: { value: string; label: string }[];
  /** The raw value to seed the edit control with. Defaults to `row[key]`. */
  editValue?: (row: T) => string;
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
  /**
   * Persist an inline edit (Checkpoint 4). Required for any column that
   * declares `editable`. Throwing keeps the cell in edit mode and shows the
   * thrown message; the table has no opinion on what counts as a validation
   * failure versus a permission one — both are just an error to display.
   */
  onCellEdit?: (row: T, key: string, value: string) => Promise<void>;
  /** Row selection (Checkpoint 4) — renders a checkbox column when set. */
  selectable?: boolean;
  selectedKeys?: Set<string>;
  onSelectionChange?: (keys: Set<string>) => void;
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
  onCellEdit,
  selectable = false,
  selectedKeys,
  onSelectionChange,
}: DataTableProps<T>) {
  const [editing, setEditing] = useState<{ row: string; col: string } | null>(null);

  const renderSortIcon = (col: ColumnDef<T>) => {
    if (!col.sortable) return null;
    const isActive = sortKey === col.key;
    if (!isActive) return <ChevronsUpDown className="ml-1 inline h-3 w-3 opacity-40" />;
    return sortDirection === 'asc'
      ? <ChevronUp className="ml-1 inline h-3 w-3" style={{ color: 'var(--accent)' }} />
      : <ChevronDown className="ml-1 inline h-3 w-3" style={{ color: 'var(--accent)' }} />;
  };

  const allSelected = selectable && data.length > 0 && data.every((row) => selectedKeys?.has(rowKey(row)));
  const someSelected = selectable && data.some((row) => selectedKeys?.has(rowKey(row)));

  function toggleAll() {
    if (!onSelectionChange) return;
    if (allSelected) {
      onSelectionChange(new Set());
    } else {
      onSelectionChange(new Set(data.map(rowKey)));
    }
  }

  function toggleOne(key: string) {
    if (!onSelectionChange || !selectedKeys) return;
    const next = new Set(selectedKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onSelectionChange(next);
  }

  return (
    <div
      className={cn('w-full overflow-x-auto', maxHeight && 'overflow-y-auto', className)}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <table className="w-full min-w-[640px] border-collapse">
        {/* Head */}
        <thead className={cn(stickyHeader && 'sticky top-0 z-10')}>
          <tr className="bd border-b">
            {selectable && (
              <th
                className={cn('w-10 px-4 py-3', stickyHeader && 'bd border-b')}
                style={stickyHeader ? { background: 'var(--surface)' } : undefined}
              >
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = !allSelected && someSelected;
                  }}
                  onChange={toggleAll}
                  className="h-4 w-4"
                  aria-label="Select all rows"
                />
              </th>
            )}
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
                {selectable && <td className="px-4 py-3" />}
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
                colSpan={columns.length + (selectable ? 1 : 0)}
                className={cn(emptyState ? 'p-4' : 'txt-faint py-16 text-center text-sm')}
              >
                {emptyState ?? emptyMessage}
              </td>
            </tr>
          ) : (
            data.map(row => {
              const key = rowKey(row);
              return (
                <tr
                  key={key}
                  className={cn(
                    'bd border-b transition-colors last:border-b-0',
                    onRowClick && 'cursor-pointer',
                  )}
                  style={{ background: 'var(--surface)' }}
                  onMouseEnter={e => { (e.currentTarget.style.background) = 'var(--surface-2)'; }}
                  onMouseLeave={e => { (e.currentTarget.style.background) = 'var(--surface)'; }}
                  onClick={() => onRowClick?.(row)}
                >
                  {selectable && (
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedKeys?.has(key) ?? false}
                        onChange={() => toggleOne(key)}
                        className="h-4 w-4"
                        aria-label="Select row"
                      />
                    </td>
                  )}
                  {columns.map(col => {
                    const isEditingThis = editing?.row === key && editing.col === col.key;
                    const canEdit = Boolean(col.editable?.(row) && onCellEdit);
                    return (
                      <td
                        key={col.key}
                        className={cn(
                          'px-4 py-3 text-[13px]',
                          col.align === 'center' && 'text-center',
                          col.align === 'right' && 'text-right',
                          col.hideBelow && hideClasses[col.hideBelow],
                          canEdit && !isEditingThis && 'cursor-text hover:bg-[var(--surface-2)]',
                        )}
                        onClick={(e) => {
                          if (!canEdit || isEditingThis) return;
                          e.stopPropagation();
                          setEditing({ row: key, col: col.key });
                        }}
                      >
                        {isEditingThis ? (
                          <EditableCell
                            row={row}
                            col={col}
                            onCancel={() => setEditing(null)}
                            onSave={async (value) => {
                              await onCellEdit!(row, col.key, value);
                              setEditing(null);
                            }}
                          />
                        ) : col.render ? (
                          col.render(row)
                        ) : (
                          <span className="txt">{String((row as unknown as Record<string, unknown>)[col.key] ?? '')}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

function EditableCell<T>({
  row,
  col,
  onSave,
  onCancel,
}: {
  row: T;
  col: ColumnDef<T>;
  onSave: (value: string) => Promise<void>;
  onCancel: () => void;
}) {
  const initial =
    col.editValue?.(row) ??
    String((row as unknown as Record<string, unknown>)[col.key] ?? '');
  const [value, setValue] = useState(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function commit() {
    // Both a real Enter-then-blur and a fast double-click can call this
    // twice before the first request returns; the second call must be a
    // no-op rather than a second PATCH for the same edit.
    if (pending) return;
    if (value === initial) {
      onCancel();
      return;
    }
    setPending(true);
    setError(null);
    try {
      await onSave(value);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save this change.');
      setPending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      void commit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
    }
  }

  return (
    <div className="relative flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      {col.editType === 'select' ? (
        <select
          autoFocus
          className="ctl w-full px-2 py-1 text-[12.5px]"
          value={value}
          disabled={pending}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => void commit()}
        >
          {(col.editOptions ?? []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          autoFocus
          type={col.editType === 'date' ? 'date' : (col.editType ?? 'text')}
          className="ctl w-full px-2 py-1 text-[12.5px]"
          value={value}
          disabled={pending}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => void commit()}
        />
      )}
      {pending ? (
        <Loader2 className="txt-faint h-3.5 w-3.5 shrink-0 animate-spin" />
      ) : (
        <>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => void commit()}
            className="shrink-0 rounded p-0.5 text-emerald-500 hover:bg-emerald-500/10"
            aria-label="Save"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={onCancel}
            className="shrink-0 rounded p-0.5 text-red-500 hover:bg-red-500/10"
            aria-label="Cancel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </>
      )}
      {error && (
        <span className="absolute mt-8 text-[11px] text-red-500" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
