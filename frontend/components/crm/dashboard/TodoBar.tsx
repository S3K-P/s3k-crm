'use client';

import { useState } from 'react';
import { ChevronUp, ClipboardList } from 'lucide-react';

import StatusBadge from '@/components/crm/shared/StatusBadge';
import { formatWhen, type DashboardTask } from '@/features/crm/dashboard';

/* ============================================================
   TODO BAR
   Floating, collapsible bottom-right utility bar. Reuses the same
   `tasks` the "Tasks & Follow-ups" card shows — one real list,
   surfaced twice, not a second data source to keep honest.
   ============================================================ */

interface TodoBarProps {
  tasks: DashboardTask[];
  now: Date;
}

export default function TodoBar({ tasks, now }: TodoBarProps) {
  const [open, setOpen] = useState(false);

  if (tasks.length === 0) return null;

  return (
    <div
      className="surface bd fixed bottom-0 right-5 z-40 flex max-h-[70vh] w-[300px] flex-col rounded-t-2xl border shadow-xl max-sm:right-3 max-sm:left-3 max-sm:w-auto"
      style={{ borderBottomWidth: 0 }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3.5 py-3 text-left"
      >
        <ClipboardList className="h-4 w-4" style={{ color: 'var(--accent)' }} />
        <span className="text-[12.5px] font-bold">To-Do List</span>
        <StatusBadge label={String(tasks.length)} variant="accent" />
        <ChevronUp
          className="ml-auto h-[15px] w-[15px] transition-transform"
          style={{ transform: open ? 'rotate(0deg)' : 'rotate(180deg)' }}
        />
      </button>

      {open && (
        <div className="space-y-0.5 overflow-y-auto px-2.5 pb-3">
          {tasks.map((task) => (
            <div key={task.id} className="flex items-start gap-2.5 rounded-lg px-1.5 py-2 hover:bg-[var(--surface-2)]">
              <div className="mt-[3px] h-[17px] w-[17px] shrink-0 rounded-[5px] border-[1.5px]" style={{ borderColor: 'var(--border)' }} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] font-semibold">{task.title}</div>
                {task.due_date && (
                  <div className="text-[11px]" style={{ color: 'var(--faint)' }}>
                    {formatWhen(task.due_date, now)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
