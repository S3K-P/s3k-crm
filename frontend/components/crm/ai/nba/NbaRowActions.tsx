'use client';

import { useEffect, useRef } from 'react';
import {
  CalendarPlus,
  CheckCircle2,
  ExternalLink,
  Eye,
  Mail,
  MessageCircle,
  MoreHorizontal,
  RefreshCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { NbaRecord } from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA ROW ACTIONS
   Follows the dropdown convention already used by the
   Opportunities table rather than rendering seven buttons per
   row. Closes on outside click, Escape and action selection.
   ============================================================ */

export type NbaAction =
  | 'view'
  | 'open-lead'
  | 'email'
  | 'whatsapp'
  | 'meeting'
  | 'complete'
  | 'regenerate';

interface NbaRowActionsProps {
  record: NbaRecord;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAction: (action: NbaAction, record: NbaRecord) => void;
  /** True while this row's recommendation is being regenerated. */
  regenerating: boolean;
}

export default function NbaRowActions({
  record,
  open,
  onOpenChange,
  onAction,
  regenerating,
}: NbaRowActionsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onOpenChange(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onOpenChange]);

  const completed = record.status === 'Completed';

  const items: { id: NbaAction; label: string; icon: typeof Eye; disabled?: boolean; title?: string }[] = [
    { id: 'view', label: 'View details', icon: Eye },
    {
      id: 'open-lead',
      label: 'Open lead',
      icon: ExternalLink,
      disabled: true,
      title: 'Demo record — no matching lead exists in the CRM yet',
    },
    { id: 'email', label: 'Generate email', icon: Mail },
    { id: 'whatsapp', label: 'Generate WhatsApp', icon: MessageCircle },
    { id: 'meeting', label: 'Schedule meeting', icon: CalendarPlus },
    {
      id: 'complete',
      label: completed ? 'Already completed' : 'Mark completed',
      icon: CheckCircle2,
      disabled: completed,
    },
    { id: 'regenerate', label: 'Regenerate recommendation', icon: RefreshCw, disabled: regenerating },
  ];

  const select = (action: NbaAction) => {
    onOpenChange(false);
    onAction(action, record);
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Actions for ${record.leadName} at ${record.company}`}
        title="Actions"
        onClick={event => {
          event.stopPropagation();
          onOpenChange(!open);
        }}
        className="ctl grid h-7 w-7 place-items-center rounded-lg transition hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
      >
        {regenerating
          ? <RefreshCw className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          : <MoreHorizontal className="h-4 w-4" aria-hidden="true" />}
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={event => {
              event.stopPropagation();
              onOpenChange(false);
            }}
          />
          <div
            role="menu"
            aria-label="Recommendation actions"
            className="surface bd absolute right-0 top-full z-20 mt-1 w-56 overflow-hidden rounded-xl border shadow-lg"
            onClick={event => event.stopPropagation()}
          >
            {items.map(item => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  role="menuitem"
                  type="button"
                  disabled={item.disabled}
                  title={item.title}
                  onClick={() => select(item.id)}
                  className={cn(
                    'flex w-full items-center gap-2.5 px-3 py-2 text-left text-[12.5px] font-medium transition-colors',
                    'hover:surface-2 focus-visible:surface-2 focus-visible:outline-none',
                    item.disabled && 'cursor-not-allowed opacity-45 hover:bg-transparent',
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
                  <span className="txt">{item.label}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
