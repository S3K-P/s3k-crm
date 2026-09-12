'use client';

import { useEffect, useState } from 'react';
import { Filter, X } from 'lucide-react';

import { cn } from '@/lib/utils';
import { FilterEditor } from '@/components/crm/reports/FilterEditor';
import {
  listCustomFields,
  type AvailableFieldInfo,
  type ReportEntity,
  type ReportFilterGroup,
} from '@/features/crm/reports/custom';

/* ============================================================
   ADVANCED FILTER BAR (Checkpoint 5)

   A multi-condition AND/OR filter for a list screen, built on
   exactly the same `ReportFilterGroup` document and the same
   `FilterEditor` the custom-report builder uses — "make filters
   reusable" taken literally rather than as a slogan. The parent
   page turns `value` into `?advanced_filter=<json>` on its list
   call; this component only edits the document and reports it
   back on Apply, so it has no opinion about how the list is
   actually fetched.

   `value`/`onApply` rather than the editor's own `onChange`
   firing on every keystroke: an advanced filter is a request the
   user assembles and then commits, not a live-typing search box —
   applying every partial edit would fire a list reload after each
   condition, most of them meaningless (an empty value, a
   half-chosen field).
   ============================================================ */

interface AdvancedFilterBarProps {
  entity: ReportEntity;
  value: ReportFilterGroup | null;
  onApply: (value: ReportFilterGroup | null) => void;
  className?: string;
}

const EMPTY_GROUP: ReportFilterGroup = { logic: 'AND', conditions: [] };

export default function AdvancedFilterBar({
  entity,
  value,
  onApply,
  className,
}: AdvancedFilterBarProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ReportFilterGroup>(value ?? EMPTY_GROUP);
  // Stamped with the entity it answers — see `ReportBuilder.tsx` for why an
  // effect that fetches on a prop change never resets state synchronously.
  const [fieldsResult, setFieldsResult] = useState<
    { entity: ReportEntity; fields: AvailableFieldInfo[] } | null
  >(null);
  const fields = fieldsResult?.entity === entity ? fieldsResult.fields : null;

  useEffect(() => {
    let cancelled = false;
    listCustomFields(entity)
      .then(list => {
        if (!cancelled) setFieldsResult({ entity, fields: list });
      })
      .catch(() => {
        // A failed field-list fetch leaves the button disabled rather than
        // broken — the list itself still renders unfiltered, which is a
        // better failure than an error blocking the whole toolbar.
      });
    return () => {
      cancelled = true;
    };
  }, [entity]);

  // The draft only needs to track the applied value when the popover opens
  // with a different filter already active elsewhere (e.g. a saved view was
  // chosen) — not on every keystroke, which is what makes this a draft.
  const openEditor = () => {
    setDraft(value ?? EMPTY_GROUP);
    setOpen(true);
  };

  const apply = () => {
    onApply(draft.conditions.length > 0 ? draft : null);
    setOpen(false);
  };

  const clear = () => {
    setDraft(EMPTY_GROUP);
    onApply(null);
    setOpen(false);
  };

  const activeCount = value?.conditions.length ?? 0;

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openEditor())}
        disabled={!fields}
        aria-expanded={open}
        className={cn(
          'ctl bd flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-semibold transition hover:opacity-80 disabled:opacity-50',
          activeCount > 0 && 'border-[var(--accent)] text-[var(--accent)]',
        )}
      >
        <Filter className="h-3.5 w-3.5" />
        Advanced filters
        {activeCount > 0 && (
          <span
            className="flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white"
            style={{ background: 'var(--accent)' }}
          >
            {activeCount}
          </span>
        )}
      </button>

      {open && fields && (
        <div className="surface bd absolute right-0 z-20 mt-1.5 w-[440px] max-w-[90vw] rounded-xl border p-3.5 shadow-lg">
          <div className="mb-2 flex items-center justify-between">
            <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">
              Match records where
            </p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="txt-faint hover:opacity-70"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <FilterEditor group={draft} fields={fields} onChange={setDraft} />

          <div className="bd mt-3 flex justify-end gap-2 border-t pt-3">
            <button
              type="button"
              onClick={clear}
              className="txt-faint hover:txt text-[12px] font-semibold"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={apply}
              className="rounded-lg px-3.5 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
