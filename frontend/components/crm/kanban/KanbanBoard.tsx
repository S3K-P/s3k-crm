'use client';

import { cn } from '@/lib/utils';
import { ReactNode, useState } from 'react';

/* ============================================================
   KANBAN BOARD
   Reusable generic Kanban board component.
   Supports generic items and custom renderers for cards.

   Drag-and-drop is native HTML5 DnD, not a library: it is the
   one interaction this board needs, and pulling in a dependency
   (e.g. @dnd-kit) is worth doing once, when custom fields and
   dashboards need sortable lists too — deliberately deferred to
   that later checkpoint rather than decided here for one board.

   Dropping never bypasses validation: `onCardDrop` is expected to
   call the same endpoint a keyboard-driven control would, so a
   Blueprint-rejected move is rejected the same way either path —
   dragging a card is a different gesture for the same request,
   not a shortcut around it. Native drag-and-drop has no keyboard
   equivalent of its own, so callers should keep an accessible
   fallback control (a select, buttons) alongside the board rather
   than relying on dragging alone — see the Opportunities page.

   **Duplicate submissions (Checkpoint 4).** `onCardDrop` may return
   its Promise instead of `void`; while it is pending, this board
   marks that one card un-draggable and dims it, so a second drop —
   a fast double-drag, or a drop that lands while the first request
   is still in flight — cannot fire a second request for the same
   record before the first resolves. A caller that still returns
   `void` (fire-and-forget) keeps its previous, unguarded behaviour;
   the guard only engages for a caller that opts in by returning the
   Promise.
   ============================================================ */

export interface KanbanColumnDef {
  id: string;
  label: string;
  color?: string; // e.g., 'var(--accent)'
}

interface KanbanBoardProps<T> {
  columns: KanbanColumnDef[];
  data: T[];
  /** Group items by a specific key */
  groupBy: (item: T) => string;
  /** Custom render function for the card */
  renderCard: (item: T) => ReactNode;
  /** Stable id for drag tracking. Required when `onCardDrop` is given. */
  getItemId?: (item: T) => string;
  /**
   * Called when a card is dropped on a different column. Omit to disable
   * dragging. Return the write's own Promise (rather than `void`) to get the
   * duplicate-submission guard described above.
   */
  onCardDrop?: (item: T, columnId: string) => void | Promise<unknown>;
  /** Whether this particular item may be dragged (e.g. not a closed deal). Defaults to true. */
  canDrag?: (item: T) => boolean;
  className?: string;
}

export default function KanbanBoard<T>({
  columns,
  data,
  groupBy,
  renderCard,
  getItemId,
  onCardDrop,
  canDrag,
  className,
}: KanbanBoardProps<T>) {
  const draggable = Boolean(onCardDrop && getItemId);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(new Set());

  const byId = (id: string): T | undefined =>
    getItemId ? data.find((item) => getItemId(item) === id) : undefined;

  return (
    <div className={cn('flex h-full w-full gap-4 overflow-x-auto pb-4', className)}>
      {columns.map(col => {
        const columnData = data.filter(item => groupBy(item) === col.id);

        return (
          <div
            key={col.id}
            onDragOver={(event) => {
              if (!draggable) return;
              event.preventDefault();
              setDragOverColumn(col.id);
            }}
            onDragLeave={() => setDragOverColumn((current) => (current === col.id ? null : current))}
            onDrop={(event) => {
              if (!draggable) return;
              event.preventDefault();
              setDragOverColumn(null);
              const droppedId = event.dataTransfer.getData('text/plain');
              if (pendingIds.has(droppedId)) return; // already moving — see module docstring
              const item = byId(droppedId);
              if (!item) return;
              const result = onCardDrop?.(item, col.id);
              if (result && typeof result.then === 'function') {
                setPendingIds((prev) => new Set(prev).add(droppedId));
                void result.finally(() => {
                  setPendingIds((prev) => {
                    const next = new Set(prev);
                    next.delete(droppedId);
                    return next;
                  });
                });
              }
            }}
            className={cn(
              'flex h-full min-w-[320px] flex-col rounded-xl bg-[var(--bg)] p-3 transition-colors',
              dragOverColumn === col.id && 'ring-2 ring-[var(--accent)] ring-inset',
            )}
          >
            {/* Column Header */}
            <div className="mb-3 flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: col.color || 'var(--border)' }}
                />
                <h3 className="txt text-[14px] font-bold">{col.label}</h3>
              </div>
              <span className="txt-faint text-[12px] font-medium">{columnData.length}</span>
            </div>

            {/* Column Cards */}
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
              {columnData.map((item, idx) => {
                const itemId = getItemId?.(item);
                const isPending = itemId !== undefined && pendingIds.has(itemId);
                const isDraggable =
                  draggable && !isPending && (canDrag ? canDrag(item) : true) && itemId !== undefined;
                return (
                  <div
                    key={itemId ?? idx}
                    draggable={isDraggable}
                    aria-busy={isPending}
                    onDragStart={(event) => {
                      if (!isDraggable || itemId === undefined) return;
                      event.dataTransfer.setData('text/plain', itemId);
                      event.dataTransfer.effectAllowed = 'move';
                      setDraggingId(itemId);
                    }}
                    onDragEnd={() => setDraggingId(null)}
                    className={cn(
                      isDraggable && 'cursor-grab active:cursor-grabbing',
                      (draggingId === itemId || isPending) && 'opacity-40',
                      isPending && 'pointer-events-none motion-safe:animate-pulse',
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
