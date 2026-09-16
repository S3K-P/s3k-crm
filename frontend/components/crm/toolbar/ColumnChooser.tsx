'use client';

import { useEffect, useRef, useState } from 'react';
import { Columns3 } from 'lucide-react';

import { cn } from '@/lib/utils';

/* ============================================================
   COLUMN CHOOSER (Checkpoint 4)

   Which of a list screen's optional columns are shown, and in
   what order. Persists through the same `SavedView.columns` the
   backend has stored since Phase F but no table read until now
   (`SavedViewPicker`'s own `columns`/`onColumnsChange` props) —
   choosing a saved view restores its column set, and saving one
   captures the current set, the same way filters and sort already
   round-trip.

   A column that cannot be hidden (typically the primary "name"
   column and the row-actions column) is simply not offered here;
   the caller decides that by what it puts in `columns`.
   ============================================================ */

export interface ColumnOption {
  key: string;
  label: string;
}

interface ColumnChooserProps {
  options: ColumnOption[];
  visible: string[];
  onChange: (keys: string[]) => void;
  className?: string;
}

export default function ColumnChooser({ options, visible, onChange, className }: ColumnChooserProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  function toggle(key: string) {
    const next = visible.includes(key) ? visible.filter((k) => k !== key) : [...visible, key];
    onChange(next);
  }

  return (
    <div ref={ref} className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        className="ctl bd flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
      >
        <Columns3 className="h-3.5 w-3.5" />
        Columns
      </button>
      {open && (
        <div className="surface bd absolute right-0 z-20 mt-1.5 w-56 rounded-xl border p-2 shadow-lg">
          <p className="txt-faint px-1.5 pb-1.5 text-[10.5px] font-bold uppercase tracking-wider">
            Visible columns
          </p>
          {options.map((option) => (
            <label
              key={option.key}
              className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 text-[12.5px] hover:bg-[var(--surface-2)]"
            >
              <input
                type="checkbox"
                checked={visible.includes(option.key)}
                onChange={() => toggle(option.key)}
                className="h-3.5 w-3.5"
              />
              <span className="txt">{option.label}</span>
            </label>
          ))}
          {visible.length === 0 && (
            <p className="txt-faint px-1.5 py-1 text-[11px]">
              All optional columns are hidden — the required ones still show.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
