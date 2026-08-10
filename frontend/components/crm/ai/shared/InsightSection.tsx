'use client';

import { useId, useState } from 'react';
import { ChevronDown, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   INSIGHT SECTION
   Collapsible card used for each generated intelligence
   category. Header carries an icon, title, one-line summary,
   an optional badge slot and an optional action (usually Copy).
   ============================================================ */

interface InsightSectionProps {
  icon: LucideIcon;
  title: string;
  /** One-line scannable summary shown in the collapsed header. */
  summary?: string;
  /** Badges or counts rendered on the right of the header. */
  meta?: React.ReactNode;
  /** Action rendered next to the chevron — typically a CopyButton. */
  action?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
}

export default function InsightSection({
  icon: Icon,
  title,
  summary,
  meta,
  action,
  defaultOpen = true,
  children,
  className,
}: InsightSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <section className={cn('surface bd overflow-hidden rounded-2xl border', className)}>
      <div className="flex items-start gap-3 px-4 py-3.5 sm:px-5">
        <button
          type="button"
          onClick={() => setOpen(value => !value)}
          aria-expanded={open}
          aria-controls={contentId}
          className="group flex min-w-0 flex-1 items-start gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded-lg"
        >
          <span
            className="surface-2 bd mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border"
            aria-hidden="true"
          >
            <Icon className="h-4 w-4" style={{ color: 'var(--accent)' }} />
          </span>

          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <h3 className="txt font-display text-[14.5px] font-bold">{title}</h3>
              <ChevronDown
                className={cn(
                  'txt-faint h-4 w-4 shrink-0 motion-safe:transition-transform motion-safe:duration-200',
                  open && 'rotate-180',
                )}
                aria-hidden="true"
              />
            </span>
            {summary && (
              <span className="txt-muted mt-0.5 block text-[12.5px] leading-snug">{summary}</span>
            )}
          </span>
        </button>

        {(meta || action) && (
          <div className="flex shrink-0 items-center gap-2 pt-0.5">
            {meta}
            {action}
          </div>
        )}
      </div>

      {open && (
        <div id={contentId} className="bd border-t px-4 py-4 sm:px-5">
          {children}
        </div>
      )}
    </section>
  );
}
