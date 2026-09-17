'use client';

import { ExternalLink, Link2, Quote, ShieldQuestion } from 'lucide-react';

import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import {
  sourceHost,
  type ResearchSource,
} from '@/features/ai/market-insights';

/* ============================================================
   SOURCES PANEL

   The evidence behind the report.

   Every row here is a page the search tool actually returned —
   the backend stores nothing it did not retrieve, and nothing
   is parsed out of the model's prose. That is what lets this
   panel be read as evidence rather than decoration (§17).

   "Cited" marks a page a sentence in the report pointed at, as
   opposed to one that was read on the way to the answer. Both
   are shown, because hiding the second kind would overstate how
   narrowly the conclusions were drawn.
   ============================================================ */

function formatRetrieved(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function SourcesPanel({
  sources,
  /** Shown when the turn completed but returned nothing (§15). */
  partial = false,
}: {
  sources: ResearchSource[];
  partial?: boolean;
}) {
  if (sources.length === 0) {
    return (
      <div className="surface bd rounded-2xl border p-4">
        <AiEmptyState
          icon={ShieldQuestion}
          size="inline"
          title="No external sources"
          description={
            partial
              ? 'External search returned nothing usable for this company, so the report draws only on the model and any CRM context. Treat it as less firmly grounded.'
              : 'This answer did not retrieve any new pages.'
          }
        />
      </div>
    );
  }

  const cited = sources.filter((source) => source.cited).length;

  return (
    <section className="surface bd overflow-hidden rounded-2xl border" aria-label="Sources">
      <header className="bd flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span
            className="surface-2 bd grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border"
            aria-hidden="true"
          >
            <Link2 className="h-4 w-4" style={{ color: 'var(--accent)' }} />
          </span>
          <div>
            <h3 className="txt font-display text-[14.5px] font-bold">Sources</h3>
            <p className="txt-muted text-[12px]">
              {sources.length} retrieved
              {cited > 0 && ` · ${cited} cited in the report`}
            </p>
          </div>
        </div>
      </header>

      <ul className="divide-y divide-[var(--border)]">
        {sources.map((source) => (
          <li key={source.id}>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-start gap-2.5 px-4 py-3 transition hover:bg-[var(--surface-2)]"
            >
              <span className="min-w-0 flex-1">
                <span className="txt block text-[13px] font-semibold leading-snug">
                  {source.title}
                </span>
                <span className="txt-faint mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11.5px]">
                  <span>{sourceHost(source.url)}</span>
                  {source.page_age && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>published {source.page_age}</span>
                    </>
                  )}
                  <span aria-hidden="true">·</span>
                  <span>retrieved {formatRetrieved(source.retrieved_at)}</span>
                </span>
              </span>

              {source.cited && (
                <span
                  className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
                  style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
                  title="A statement in the report cites this page"
                >
                  <Quote className="h-2.5 w-2.5" aria-hidden="true" />
                  Cited
                </span>
              )}

              <ExternalLink
                className="txt-faint mt-0.5 h-3.5 w-3.5 shrink-0 opacity-0 transition group-hover:opacity-100"
                aria-hidden="true"
              />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
