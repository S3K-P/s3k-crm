'use client';

import { cn } from '@/lib/utils';
import { Circle, CheckCircle2 } from 'lucide-react';

/* ============================================================
   TASK CARD
   Individual task item with priority badge, due time, and
   completion state. Reusable in Dashboard, Lead detail, etc.
   ============================================================ */

export type TaskPriority = 'high' | 'medium' | 'low';

export interface TaskItem {
  id: string;
  title: string;
  /** e.g. "Follow up with Acme Corp" */
  description?: string;
  priority: TaskPriority;
  /** e.g. "10:00 AM" or "2:30 PM" */
  dueTime?: string;
  completed?: boolean;
  /** Related entity e.g. "Acme Corp" */
  relatedTo?: string;
}

interface TaskCardProps {
  task: TaskItem;
  onToggle?: (id: string) => void;
  className?: string;
}

const priorityConfig: Record<TaskPriority, { label: string; bg: string; color: string; dot: string }> = {
  high:   { label: 'High',   bg: '#fef2f2', color: '#dc2626', dot: 'bg-red-500' },
  medium: { label: 'Medium', bg: '#fffbeb', color: '#d97706', dot: 'bg-amber-500' },
  low:    { label: 'Low',    bg: '#ecfdf5', color: '#059669', dot: 'bg-emerald-500' },
};

export default function TaskCard({ task, onToggle, className }: TaskCardProps) {
  const p = priorityConfig[task.priority];

  return (
    <div className={cn(
      'surface bd flex items-start gap-3 rounded-xl border px-3.5 py-3 transition-all hover:shadow-sm',
      task.completed && 'opacity-60',
      className,
    )}>
      {/* Status circle — interactive only when the caller can persist a change.
          Without `onToggle` there is nothing to toggle, and rendering a button
          that silently does nothing would advertise an action the app cannot
          perform. */}
      {onToggle ? (
        <button
          type="button"
          onClick={() => onToggle(task.id)}
          aria-pressed={task.completed ?? false}
          aria-label={task.completed ? `Reopen ${task.title}` : `Complete ${task.title}`}
          className="mt-0.5 shrink-0 transition hover:scale-110"
          style={{ color: task.completed ? 'var(--accent)' : 'var(--border)' }}
        >
          {task.completed
            ? <CheckCircle2 className="h-[18px] w-[18px]" />
            : <Circle className="h-[18px] w-[18px]" />
          }
        </button>
      ) : (
        <span
          className="mt-0.5 shrink-0"
          style={{ color: task.completed ? 'var(--accent)' : 'var(--border)' }}
          aria-hidden="true"
        >
          {task.completed
            ? <CheckCircle2 className="h-[18px] w-[18px]" />
            : <Circle className="h-[18px] w-[18px]" />
          }
        </span>
      )}

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={cn(
            'txt text-[13px] font-semibold leading-tight',
            task.completed && 'line-through',
          )}>
            {task.title}
          </span>
          <span
            className="inline-flex items-center gap-1 rounded-full px-2 py-[1px] text-[10px] font-bold uppercase"
            style={{ background: p.bg, color: p.color }}
          >
            <span className={cn('h-1.5 w-1.5 rounded-full', p.dot)} />
            {p.label}
          </span>
        </div>
        {task.description && (
          <p className="txt-muted mt-0.5 text-[12px] leading-snug">{task.description}</p>
        )}
        <div className="mt-1 flex items-center gap-3">
          {task.dueTime && (
            <span className="txt-faint text-[11px] font-medium">{task.dueTime}</span>
          )}
          {task.relatedTo && (
            <span className="txt-faint text-[11px]">
              · {task.relatedTo}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
