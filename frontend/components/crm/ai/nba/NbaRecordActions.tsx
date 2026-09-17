'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ArrowUpRight } from 'lucide-react';

import { describeApiError } from '@/features/shared/hooks/useCollection';
import { nbaForRecord, type NbaRecordKind, type PriorityScore } from '@/features/ai/ai-insights';
import NbaEngineActions from './NbaEngineActions';

/* ============================================================
   NBA RECORD ACTIONS

   The engine's actions for the Opportunity/Lead 360 page, read
   from `GET /nba/{opportunities,leads}/{id}` — rules and history,
   no model call. Read-only here: "Act on these" opens the record
   in the Next Best Action queue, where they are carried out,
   drafted, done or dismissed.
   ============================================================ */

type Loaded = { status: 'ready'; item: PriorityScore | null } | { status: 'error'; message: string };

export default function NbaRecordActions({ kind, id }: { kind: NbaRecordKind; id: string }) {
  const [loaded, setLoaded] = useState<{ key: string; value: Loaded } | null>(null);
  const key = `${kind}:${id}`;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const item = await nbaForRecord(kind, id);
        if (!cancelled) setLoaded({ key: `${kind}:${id}`, value: { status: 'ready', item } });
      } catch (caught) {
        if (!cancelled) {
          setLoaded({
            key: `${kind}:${id}`,
            value: { status: 'error', message: describeApiError(caught, 'Could not load the recommended actions.') },
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [kind, id]);

  const current = loaded?.key === key ? loaded.value : null;

  if (!current) return <p className="txt-muted text-[12.5px]">Loading recommended actions…</p>;
  if (current.status === 'error') return <p className="text-[12px] text-rose-600">{current.message}</p>;
  if (!current.item) {
    return <p className="txt-muted text-[12.5px]">Closed records have no next best action.</p>;
  }

  return (
    <div className="space-y-2">
      <NbaEngineActions item={current.item} />
      {current.item.actions.length > 0 && (
        <Link
          href={`/ai/next-best-action?record=${encodeURIComponent(id)}`}
          className="inline-flex items-center gap-1 text-[12px] font-semibold transition hover:opacity-80"
          style={{ color: 'var(--accent)' }}
        >
          Act on these in the queue <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      )}
    </div>
  );
}
