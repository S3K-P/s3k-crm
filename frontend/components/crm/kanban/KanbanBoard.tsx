'use client';

import { cn } from '@/lib/utils';
import { ReactNode, useState } from 'react';

/* ============================================================
   KANBAN BOARD

   A board is only worth having over a table for two reasons, and
   this component exists to provide both (analysis §3.5):

   1. **Direct manipulation.** Dragging a card to another column
      changes the record. Opening an edit form to change one field
      is the cycle a board is supposed to remove.
   2. **Aggregate per column.** A count answers "how many"; a
      sales manager is asking "how much". `aggregate` sums a value
      per column so the board shows what the stage is worth.

   Drag-and-drop is the HTML5 API rather than a library: the whole
   interaction is dragstart, dragover, drop, and pulling in a
   dependency for three event handlers is not a trade worth making.
   The select on each card stays as the keyboard-accessible path —
   dragging is an accelerator, never the only way to do something.
   ============================================================ */

export interface KanbanColumnDef<T> {
  id: string;
  label: string;
  color?: string; // e.g., 'var(--accent)'
  /** Shown under the column header, e.g. what entering this stage requires. */
  hint?: string;
}

interface KanbanBoardProps<T> {
  columns: KanbanColumnDef<T>[];
  data: T[];
  /** Group items by a specific key */
  groupBy: (item: T) => string;
  /** Custom render function for the card */
  renderCard: (item: T) => ReactNode;
  /** Stable identity for an item, required for drag-and-drop. */
  getId?: (item: T) => string;
  /**
   * Move an item to another column. Returning a rejected promise (or throwing)
   * leaves the card where it was — the board does not assume the write
   * succeeded, because a stage move can be refused by stage requirements.
   */
  onMove?: (item: T, columnId: string) => void | Promise<void>;
  /** Per-item numeric contribution to its column's total. */
  aggregate?: (item: T) => number;
  /** Renders a column total. Given the summed `aggregate` values. */
  formatAggregate?: (total: number) => string;
  className?: string;
}

export default function KanbanBoard<T>({
  columns,
  data,
  groupBy,
  renderCard,
  getId,
  onMove,
  aggregate,
  formatAggregate,
  className,
}: KanbanBoardProps<T>) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overColumn, setOverColumn] = useState<string | null>(null);

  const canDrag = Boolean(onMove && getId);

  const handleDrop = async (columnId: string) => {
    setOverColumn(null);
    const id = draggingId;
    setDraggingId(null);
    if (!id || !onMove || !getId) return;

    const item = data.find((candidate) => getId(candidate) === id);
    // Dropping a card back where it came from is a no-op, not a write.
    if (!item || groupBy(item) === columnId) return;
    await onMove(item, columnId);
  };

  return (
    <div className={cn('flex h-full w-full gap-4 overflow-x-auto pb-4', className)}>
      {columns.map((col) => {
        const columnData = data.filter((item) => groupBy(item) === col.id);
        const total = aggregate
          ? columnData.reduce((sum, item) => sum + aggregate(item), 0)
          : null;

        return (
          <div
            key={col.id}
            onDragOver={(event) => {
              if (!canDrag) return;
              // Without preventDefault the browser refuses the drop entirely.
              event.preventDefault();
              setOverColumn(col.id);
            }}
            onDragLeave={() => setOverColumn((current) => (current === col.id ? null : current))}
            onDrop={(event) => {
              if (!canDrag) return;
              event.preventDefault();
              void handleDrop(col.id);
            }}
            className={cn(
              'flex h-full min-w-[320px] flex-col rounded-xl bg-[var(--bg)] p-3 transition',
              overColumn === col.id && 'ring-2 ring-[var(--accent)] ring-offset-1',
            )}
          >
            {/* Column Header */}
            <div className="mb-3 px-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: col.color || 'var(--border)' }}
                  />
                  <h3 className="txt text-[14px] font-bold">{col.label}</h3>
                </div>
                <span className="txt-faint text-[12px] font-medium">{columnData.length}</span>
              </div>
              {total !== null && formatAggregate && (
                <p className="txt-muted mt-0.5 pl-4 text-[12px] font-semibold">
                  {formatAggregate(total)}
                </p>
              )}
              {col.hint && (
                <p className="txt-faint mt-0.5 pl-4 text-[11.5px]">Needs {col.hint}</p>
              )}
            </div>

            {/* Column Cards */}
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
              {columnData.map((item, idx) => {
                const id = getId ? getId(item) : String(idx);
                return (
                  <div
                    key={id}
                    draggable={canDrag}
                    onDragStart={() => setDraggingId(id)}
                    onDragEnd={() => {
                      setDraggingId(null);
                      setOverColumn(null);
                    }}
                    className={cn(
                      canDrag && 'cursor-grab active:cursor-grabbing',
                      draggingId === id && 'opacity-50',
                    )}
                  >
                    {renderCard(item)}
                  </div>
                );
              })}
              {columnData.length === 0 && (
                <div className="txt-faint flex flex-1 items-center justify-center rounded-xl border border-dashed border-[var(--border)] p-4 text-[13px]">
                  No items
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
