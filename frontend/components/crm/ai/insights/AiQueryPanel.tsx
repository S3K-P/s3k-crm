'use client';

import { BrainCircuit, Clock, Loader2, Search, Sparkles, X } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   AI QUERY PANEL
   The query workspace at the top of AI Insights: input,
   generate/clear actions, suggested prompts and recent
   searches. Purely presentational — all state is owned by the
   page so the panel stays reusable.
   ============================================================ */

interface AiQueryPanelProps {
  query: string;
  onQueryChange: (value: string) => void;
  onGenerate: () => void;
  onClear: () => void;
  suggestedPrompts: string[];
  recentSearches: string[];
  loading: boolean;
  /** True once a result (or error) is on screen — enables Clear. */
  hasResult: boolean;
  error: string | null;
}

export default function AiQueryPanel({
  query,
  onQueryChange,
  onGenerate,
  onClear,
  suggestedPrompts,
  recentSearches,
  loading,
  hasResult,
  error,
}: AiQueryPanelProps) {
  const blank = query.trim().length === 0;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && !loading && !blank) {
      event.preventDefault();
      onGenerate();
    }
  };

  return (
    <div className="surface bd rounded-2xl border p-4 sm:p-5">
      {/* ── Query input ── */}
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search
            className="txt-faint pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2"
            aria-hidden="true"
          />
          <input
            id="ai-insights-query"
            type="text"
            value={query}
            onChange={event => onQueryChange(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-label="Search a lead, company or opportunity, or ask a question about your CRM"
            aria-describedby={error ? 'ai-insights-query-error' : undefined}
            aria-invalid={error ? true : undefined}
            placeholder="Search Lead, Company, Opportunity or ask AI for CRM insights..."
            className={cn(
              'ctl w-full py-2.5 pl-10 pr-9 text-[13.5px] outline-none transition-colors',
              'focus:border-[var(--accent)] disabled:opacity-60',
              error && 'border-red-500 focus:border-red-500',
            )}
          />
          {query && !loading && (
            <button
              type="button"
              onClick={() => onQueryChange('')}
              aria-label="Clear query text"
              className="txt-faint absolute right-3 top-1/2 -translate-y-1/2 rounded transition hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onGenerate}
            disabled={loading || blank}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
            style={{ background: 'var(--accent)' }}
          >
            {loading
              ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
              : <Sparkles className="h-4 w-4" aria-hidden="true" />}
            {loading ? 'Generating…' : 'Generate Insights'}
          </button>

          <button
            type="button"
            onClick={onClear}
            disabled={loading || (blank && !hasResult)}
            className="ctl px-4 py-2.5 text-[13px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Clear
          </button>
        </div>
      </div>

      {error && (
        <p id="ai-insights-query-error" role="alert" className="mt-2 text-[12px] font-medium text-red-500">
          {error}
        </p>
      )}

      {/* ── Suggested prompts ── */}
      <div className="mt-4">
        <p className="txt-faint mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider">
          <BrainCircuit className="h-3.5 w-3.5" aria-hidden="true" />
          Suggested prompts
        </p>
        <div className="flex flex-wrap gap-1.5">
          {suggestedPrompts.map(prompt => (
            <button
              key={prompt}
              type="button"
              onClick={() => onQueryChange(prompt)}
              disabled={loading}
              className="ctl txt-muted rounded-full px-3 py-1.5 text-[12px] font-medium transition hover:border-[var(--accent)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* ── Recent searches ── */}
      {recentSearches.length > 0 && (
        <div className="bd mt-4 border-t pt-3.5">
          <p className="txt-faint mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            Recent searches
          </p>
          <div className="flex flex-wrap gap-1.5">
            {recentSearches.map(recent => (
              <button
                key={recent}
                type="button"
                onClick={() => onQueryChange(recent)}
                disabled={loading}
                className="txt-muted surface-2 bd max-w-full truncate rounded-lg border px-2.5 py-1 text-[12px] font-medium transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                title={recent}
              >
                {recent}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
