'use client';

import type { HTMLAttributes, ReactNode } from 'react';
import { GripVertical, X, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   DASHBOARD CARD
   Shared shell for every card on the home dashboard: icon, title,
   header actions, an optional toolbar row, the body, and a footer
   that says when the data was last fetched.

   Customize mode is opt-in per render, not a separate component —
   a card does not know whether it is being dragged, only that the
   page asked it to show a drag handle and a remove button.
   ============================================================ */

interface DashboardCardProps {
  icon: LucideIcon;
  title: string;
  /** Buttons/menus in the card header, e.g. "new" and "more". */
  headerActions?: ReactNode;
  /** A toolbar row under the header, e.g. a scope select + inline search. */
  toolbar?: ReactNode;
  /** When this card's own data was last fetched successfully. */
  fetchedAt?: Date | null;
  /** Footer link, e.g. "View all →". Omitted when there is nowhere to go. */
  footerHref?: string;
  footerLabel?: string;
  /** Spans the full row width — used by the wide Activity Timeline card. */
  wide?: boolean;
  /** Shows the drag handle and remove control, and a dashed outline. */
  isCustomizing?: boolean;
  onRemove?: () => void;
  /** Props from a dnd-kit `useSortable()` for the drag handle only. */
  dragHandleProps?: HTMLAttributes<HTMLButtonElement>;
  className?: string;
  style?: React.CSSProperties;
  children: ReactNode;
}

function formatAsOf(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

export default function DashboardCard({
  icon: Icon,
  title,
  headerActions,
  toolbar,
  fetchedAt,
  footerHref,
  footerLabel = 'View all',
  wide = false,
  isCustomizing = false,
  onRemove,
  dragHandleProps,
  className,
  style,
  children,
}: DashboardCardProps) {
  return (
    <div
      className={cn(
        'surface bd relative flex h-[400px] flex-col rounded-2xl border transition-shadow',
        wide && 'md:col-span-2 xl:col-span-3',
        isCustomizing && 'outline outline-2 outline-dashed outline-offset-[3px]',
        className,
      )}
      style={{ ...style, ...(isCustomizing ? { outlineColor: 'var(--accent)' } : {}) }}
    >
      {isCustomizing && onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${title} card`}
          className="absolute -right-2.5 -top-2.5 z-10 flex h-6 w-6 items-center justify-center rounded-full border-2 bg-red-600 text-white shadow-md transition hover:bg-red-700"
          style={{ borderColor: 'var(--surface)' }}
        >
          <X className="h-3.5 w-3.5" strokeWidth={2.5} />
        </button>
      )}

      <div className="flex shrink-0 items-center gap-2.5 px-4 pt-[15px]">
        {isCustomizing && (
          <button
            type="button"
            aria-label={`Drag to reorder ${title}`}
            className="shrink-0 cursor-grab touch-none"
            style={{ color: 'var(--faint)' }}
            {...dragHandleProps}
          >
            <GripVertical className="h-[15px] w-[15px]" />
          </button>
        )}
        <div
          className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px]"
          style={{ background: 'var(--surface-2)', color: 'var(--accent)' }}
        >
          <Icon className="h-[15px] w-[15px]" />
        </div>
        <h3 className="txt text-[14px] font-bold">{title}</h3>
        {headerActions && (
          <div className="ml-auto flex shrink-0 items-center gap-1.5">{headerActions}</div>
        )}
      </div>

      {toolbar && <div className="flex shrink-0 items-center gap-2 px-4 pt-2.5">{toolbar}</div>}

      <div className="flex-1 overflow-y-auto px-2 pb-1.5 pt-2.5">{children}</div>

      <div
        className="bd mt-1.5 flex shrink-0 items-center justify-between border-t px-4 py-2.5 text-[11px]"
        style={{ color: 'var(--faint)' }}
      >
        {footerHref ? (
          <a
            href={footerHref}
            className="text-[11px] font-bold hover:opacity-80"
            style={{ color: 'var(--accent)' }}
          >
            {footerLabel}
          </a>
        ) : (
          <span />
        )}
        <span>{fetchedAt ? `As of ${formatAsOf(fetchedAt)}` : ''}</span>
      </div>
    </div>
  );
}
