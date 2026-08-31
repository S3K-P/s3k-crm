'use client';

import { useEffect, useState } from 'react';
import { Check, Loader2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import AiInsightsSkeleton from '@/components/crm/ai/insights/AiInsightsSkeleton';

/* ============================================================
   RESEARCH PROGRESS

   Research is one long request — the model searches, reads and
   writes before anything comes back — so there is no real
   per-stage signal to report. Rather than invent one, the
   stages advance on a timer and are worded as intent
   ("Gathering company information") rather than as measurement
   ("Found 12 sources"). Nothing here claims a step has
   completed on the server.

   The last stage stays pending however long the request takes,
   so the interface never shows a finished list while the answer
   is still coming.
   ============================================================ */

const STAGES = [
  'Identifying the company',
  'Gathering company information',
  'Analysing market position',
  'Reviewing competitors and recent developments',
  'Generating insights',
] as const;

/** Roughly matched to a typical research turn; the last stage holds. */
const STAGE_MS = 6_000;

export default function ResearchProgress({ companyName }: { companyName: string }) {
  const [stage, setStage] = useState(0);

  // No reset here: the parent keys this component by company name, so a new
  // subject remounts it with `stage` already at 0. Resetting state inside an
  // effect would be a second, redundant source of truth for the same thing.
  useEffect(() => {
    const timer = setInterval(() => {
      setStage((current) => Math.min(current + 1, STAGES.length - 1));
    }, STAGE_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="space-y-4" aria-live="polite" aria-busy="true">
      <div className="surface bd rounded-2xl border p-5">
        <p className="txt font-display flex items-center gap-2 text-[15px] font-bold">
          <Loader2
            className="h-4 w-4 motion-safe:animate-spin"
            style={{ color: 'var(--accent)' }}
            aria-hidden="true"
          />
          Researching {companyName}…
        </p>
        <p className="txt-muted mt-1 text-[12.5px]">
          Searching current sources and building the intelligence report. This usually takes
          under a minute.
        </p>

        <ol className="mt-4 space-y-2">
          {STAGES.map((label, index) => {
            const done = index < stage;
            const active = index === stage;
            return (
              <li key={label} className="flex items-center gap-2.5">
                <span
                  className={cn(
                    'grid h-5 w-5 shrink-0 place-items-center rounded-full border',
                    done ? 'border-transparent' : 'bd',
                  )}
                  style={done ? { background: 'var(--accent)' } : undefined}
                  aria-hidden="true"
                >
                  {done ? (
                    <Check className="h-3 w-3 text-white" />
                  ) : active ? (
                    <Loader2
                      className="h-3 w-3 motion-safe:animate-spin"
                      style={{ color: 'var(--accent)' }}
                    />
                  ) : null}
                </span>
                <span
                  className={cn(
                    'text-[12.5px]',
                    done || active ? 'txt font-medium' : 'txt-faint',
                  )}
                >
                  {label}
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      <AiInsightsSkeleton />
    </div>
  );
}
