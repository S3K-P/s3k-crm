'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity as ActivityIcon,
  ArrowRightLeft,
  CheckSquare2,
  Loader2,
  Mail,
  StickyNote,
  Target,
  UserPlus,
  type LucideIcon,
} from 'lucide-react';

import { describeApiError } from '@/features/shared/hooks/useCollection';
import type { TimelineEntry, TimelineEntryKind } from '@/features/shared/types/api';

/* ============================================================
   RECORD TIMELINE

   The unified, merged, newest-first timeline shared by the
   Account, Contact and Opportunity detail pages — one component
   parameterized by whichever `/timeline` endpoint the caller
   passes in, so the three record types share one rendering (and
   one set of empty/loading/error states) instead of three copies
   of the same list.

   Each event kind is read through its owning module's own
   authorization (private notes, another user's drafts, record
   visibility) rather than a copy of it — see
   `backend/app/products/crm/shared/timeline.py`.
   ============================================================ */

const ICONS: Record<TimelineEntryKind, LucideIcon> = {
  activity: ActivityIcon,
  deal_created: Target,
  stage_changed: ArrowRightLeft,
  contact_created: UserPlus,
  task_created: CheckSquare2,
  task_completed: CheckSquare2,
  email_sent: Mail,
  note_added: StickyNote,
};

const ROUTES: Record<string, (id: string) => string> = {
  CONTACT: (id) => `/contacts/${id}`,
  OPPORTUNITY: (id) => `/opportunities/${id}`,
};

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface RecordTimelineProps {
  /** Reads the merged timeline for one record, e.g. `() => getContactTimeline(id)`. */
  fetchEntries: (limit: number) => Promise<TimelineEntry[]>;
  /** Re-fetches when this changes — pass an id, or an id plus a refresh token. */
  dependencyKey: string;
  limit?: number;
  emptyMessage?: string;
}

export default function RecordTimeline({
  fetchEntries,
  dependencyKey,
  limit = 100,
  emptyMessage = 'Nothing has happened on this record yet.',
}: RecordTimelineProps) {
  const router = useRouter();
  const [items, setItems] = useState<TimelineEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await fetchEntries(limit);
        if (!cancelled) {
          setItems(result);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load the timeline.'));
      }
    })();
    return () => {
      cancelled = true;
    };
    // `fetchEntries` is a fresh closure every render; `dependencyKey` is what
    // actually identifies "which record, at what point in time" and is the
    // caller's contract for when to re-fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dependencyKey, limit]);

  if (error !== null) {
    return <p className="text-[12.5px] text-red-500">{error}</p>;
  }

  if (items === null) {
    return (
      <p className="txt-muted flex items-center gap-2 py-8 text-[13px]">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading timeline…
      </p>
    );
  }

  if (items.length === 0) {
    return <p className="txt-faint py-8 text-center text-[13px]">{emptyMessage}</p>;
  }

  return (
    <ol className="space-y-4">
      {items.map((entry) => {
        const Icon = ICONS[entry.kind];
        const openTarget = ROUTES[entry.entity_type];
        return (
          <li key={`${entry.kind}-${entry.entity_id}-${entry.occurred_at}`} className="flex gap-3">
            <div
              className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
              style={{ background: 'var(--surface-2)' }}
              aria-hidden="true"
            >
              <Icon className="h-3.5 w-3.5" style={{ color: 'var(--accent)' }} />
            </div>
            <div className="min-w-0 flex-1 pb-1">
              {openTarget ? (
                <button
                  type="button"
                  onClick={() => router.push(openTarget(entry.entity_id))}
                  className="txt text-left text-[13px] font-semibold hover:underline"
                >
                  {entry.title}
                </button>
              ) : (
                <p className="txt text-[13px] font-semibold">{entry.title}</p>
              )}
              {entry.detail && <p className="txt-muted mt-0.5 text-[12.5px]">{entry.detail}</p>}
              <p className="txt-faint mt-0.5 text-[11.5px]">{formatWhen(entry.occurred_at)}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
