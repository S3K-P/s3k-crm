'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  ArrowUpRight,
  CalendarPlus,
  ChevronDown,
  ListTodo,
  Mail,
  Phone,
  type LucideIcon,
} from 'lucide-react';

import { usePermissions } from '@/context/AuthContext';
import type { PriorityScore } from '@/features/ai/ai-insights';
import { cn } from '@/lib/utils';
import { recordHref } from './nba-view';

/* ============================================================
   NBA TAKE ACTION

   Every entry is an existing CRM flow, filed against the record:

   - Email      the CRM composer (`POST /crm/emails`), AI drafting
                included — nothing is sent without the rep
   - Meeting    `POST /crm/activities` with a meeting extension
   - Task       `POST /crm/tasks`
   - Call       the device dialer, for a lead with a phone number
   - Open       the record itself

   Each is shown only to someone allowed to do it. When none of
   the executable flows is available, the button is simply a link
   to the record — it never pretends to act.
   ============================================================ */

export type NbaActionKind = 'email' | 'meeting' | 'task';

interface MenuEntry {
  id: string;
  label: string;
  icon: LucideIcon;
  onSelect?: () => void;
  href?: string;
}

export default function NbaTakeActionMenu({
  item,
  onAction,
  align = 'right',
  placement = 'auto',
}: {
  item: PriorityScore;
  onAction: (kind: NbaActionKind, item: PriorityScore) => void;
  align?: 'left' | 'right';
  /** `auto` opens upward on phones and downward from `sm`; `up` always opens upward (drawer footers). */
  placement?: 'auto' | 'up';
}) {
  const { can } = usePermissions();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const entries: MenuEntry[] = [];
  if (can('emails', 'CREATE')) {
    entries.push({ id: 'email', label: 'Send an email', icon: Mail, onSelect: () => onAction('email', item) });
  }
  if (can('activities', 'CREATE')) {
    entries.push({
      id: 'meeting',
      label: 'Schedule a meeting',
      icon: CalendarPlus,
      onSelect: () => onAction('meeting', item),
    });
  }
  if (can('tasks', 'CREATE')) {
    entries.push({
      id: 'task',
      label: 'Create follow-up task',
      icon: ListTodo,
      onSelect: () => onAction('task', item),
    });
  }
  if (item.entity_type === 'LEAD' && item.facts.phone) {
    entries.push({ id: 'call', label: `Call ${item.facts.phone}`, icon: Phone, href: `tel:${item.facts.phone}` });
  }

  const primaryClass =
    'inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2';

  if (entries.length === 0) {
    return (
      <Link href={recordHref(item)} className={primaryClass} style={{ background: 'var(--accent)' }}>
        Take action <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
      </Link>
    );
  }

  entries.push({ id: 'open', label: 'Open record', icon: ArrowUpRight, href: recordHref(item) });

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={primaryClass}
        style={{ background: 'var(--accent)' }}
      >
        Take action <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" aria-hidden="true" onClick={() => setOpen(false)} />
          <div
            role="menu"
            aria-label={`Actions for ${item.entity_label}`}
            className={cn(
              'surface bd absolute bottom-full z-20 mb-1.5 w-60 overflow-hidden rounded-xl border py-1 shadow-lg',
              placement === 'auto' && 'sm:bottom-auto sm:top-full sm:mb-0 sm:mt-1.5',
              align === 'right' ? 'right-0' : 'left-0',
            )}
          >
            {entries.map((entry) => {
              const Icon = entry.icon;
              const body = (
                <>
                  <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
                  <span className="txt truncate">{entry.label}</span>
                </>
              );
              const className =
                'flex w-full items-center gap-2.5 px-3 py-2 text-left text-[12.5px] font-medium transition-colors hover:bg-[var(--surface-2)] focus-visible:bg-[var(--surface-2)] focus-visible:outline-none';
              if (entry.href) {
                const external = entry.href.startsWith('tel:');
                return external ? (
                  <a key={entry.id} role="menuitem" href={entry.href} className={className} onClick={() => setOpen(false)}>
                    {body}
                  </a>
                ) : (
                  <Link key={entry.id} role="menuitem" href={entry.href} className={className} onClick={() => setOpen(false)}>
                    {body}
                  </Link>
                );
              }
              return (
                <button
                  key={entry.id}
                  role="menuitem"
                  type="button"
                  className={className}
                  onClick={() => {
                    setOpen(false);
                    entry.onSelect?.();
                  }}
                >
                  {body}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
