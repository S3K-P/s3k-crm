'use client';

import { useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   FORM SECTION
   Collapsible, bordered group of fields inside a create/edit
   drawer — mirrors `design-mockups/shared/form-helpers.js`'s
   `.form-section` (header bar + 2-column body), the grouping the
   approved gallery mockups use for every module's form (Basic
   Info / Get in Touch / Address / Professional Info / ...).
   ============================================================ */

interface FormSectionProps {
  title: string;
  children: ReactNode;
  /** Starts collapsed — for lower-priority groups (e.g. Description). */
  defaultCollapsed?: boolean;
  className?: string;
}

export default function FormSection({
  title,
  children,
  defaultCollapsed = false,
  className,
}: FormSectionProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className={cn('bd overflow-hidden rounded-xl border', className)}>
      <button
        type="button"
        onClick={() => setCollapsed((value) => !value)}
        aria-expanded={!collapsed}
        className="surface-2 flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <span className="txt text-[12.5px] font-bold">{title}</span>
        <ChevronDown
          className={cn(
            'txt-faint ml-auto h-4 w-4 shrink-0 transition-transform',
            collapsed && '-rotate-90',
          )}
        />
      </button>
      {!collapsed && (
        <div className="grid grid-cols-1 gap-3.5 p-4 sm:grid-cols-2">{children}</div>
      )}
    </div>
  );
}
