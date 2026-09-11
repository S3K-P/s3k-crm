'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity as ActivityIcon,
  ArrowRightLeft,
  Loader2,
  Target,
  UserPlus,
  type LucideIcon,
} from 'lucide-react';

import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  getAccountTimeline,
  type AccountTimelineEntry,
  type AccountTimelineEntryKind,
} from '@/features/crm/accounts';

/* ============================================================
   ACCOUNT TIMELINE

   Every event this caller may see against this account, merged
   and newest first — logged activities, deals created, stage
   moves, and contacts added. Notes are not a source: their
   visibility (private / team / organization) is the notes
   module's own policy and is read correctly on the Notes tab
   instead of being re-derived here.
   ============================================================ */

const ICONS: Record<AccountTimelineEntryKind, LucideIcon> = {
  activity: ActivityIcon,
  deal_created: Target,
  stage_changed: ArrowRightLeft,
  contact_created: UserPlus,
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

export default function AccountTimeline({ accountId }: { accountId: string }) {
  const router = useRouter();
  const [items, setItems] = useState<AccountTimelineEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getAccountTimeline(accountId, 100);
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
  }, [accountId]);

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
    return (
      <p className="txt-faint py-8 text-center text-[13px]">
        Nothing has happened on this account yet. Activity, deals and contacts will appear here as
        they are recorded.
      </p>
    );
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
