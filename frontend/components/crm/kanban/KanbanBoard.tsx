'use client';

import { cn } from '@/lib/utils';
import { ReactNode } from 'react';

/* ============================================================
   KANBAN BOARD
   Reusable generic Kanban board component.
   Supports generic items and custom renderers for cards.
   ============================================================ */

export interface KanbanColumnDef<T> {
  id: string;
  label: string;
  color?: string; // e.g., 'var(--accent)'
}

interface KanbanBoardProps<T> {
  columns: KanbanColumnDef<T>[];
  data: T[];
  /** Group items by a specific key */
  groupBy: (item: T) => string;
  /** Custom render function for the card */
  renderCard: (item: T) => ReactNode;
  className?: string;
}

export default function KanbanBoard<T>({
  columns,
  data,
  groupBy,
  renderCard,
  className,
}: KanbanBoardProps<T>) {
  return (
    <div className={cn('flex h-full w-full gap-4 overflow-x-auto pb-4', className)}>
      {columns.map(col => {
        const columnData = data.filter(item => groupBy(item) === col.id);
        
        return (
          <div key={col.id} className="flex h-full min-w-[320px] flex-col rounded-xl bg-[var(--bg)] p-3">
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
              {columnData.map((item, idx) => (
                <div key={idx}>
                  {renderCard(item)}
                </div>
              ))}
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
