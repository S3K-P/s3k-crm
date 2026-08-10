'use client';

import { useCallback, useMemo, useState } from 'react';
import { AlertCircle, BrainCircuit, RotateCcw, SearchX, Sparkles } from 'lucide-react';
import AiQueryPanel from '@/components/crm/ai/insights/AiQueryPanel';
import AiInsightsSkeleton from '@/components/crm/ai/insights/AiInsightsSkeleton';
import AiExecutiveSummary from '@/components/crm/ai/insights/AiExecutiveSummary';
import AiInsightsReport from '@/components/crm/ai/insights/AiInsightsReport';
import SalesIntelligenceSnapshot from '@/components/crm/ai/insights/SalesIntelligenceSnapshot';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import {
  ANALYSIS_CAPABILITIES,
  SUGGESTED_PROMPTS,
  generateMockAIInsights,
  getSalesIntelligenceSnapshot,
  type AiInsightResult,
} from '@/features/ai/insights';

/* ============================================================
   AI INSIGHTS
   Enterprise intelligence workspace. Everything on this page
   resolves locally against the demonstration dataset — there
   are no API routes, server actions or AI provider calls.
   ============================================================ */

const MAX_RECENT_SEARCHES = 5;

export default function AiInsightsPage() {
  const [query, setQuery] = useState('');
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [result, setResult] = useState<AiInsightResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState('');

  // The snapshot is portfolio-level and independent of the query, so it is
  // derived once rather than on every render.
  const snapshot = useMemo(() => getSalesIntelligenceSnapshot(), []);

  const runGeneration = useCallback(async (raw: string) => {
    const trimmed = raw.trim();

    if (trimmed.length === 0) {
      setValidationError('Enter a lead, company, opportunity or question to generate insights.');
      return;
    }

    setValidationError(null);
    setGenerationError(null);
    setLoading(true);
    setLastQuery(trimmed);

    try {
      const generated = await generateMockAIInsights(trimmed);
      setResult(generated);
      setRecentSearches(previous =>
        [trimmed, ...previous.filter(item => item !== trimmed)].slice(0, MAX_RECENT_SEARCHES),
      );
    } catch {
      setResult(null);
      setGenerationError('Insights could not be generated. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleGenerate = useCallback(() => {
    void runGeneration(query);
  }, [query, runGeneration]);

  const handleRetry = useCallback(() => {
    void runGeneration(lastQuery || query);
  }, [lastQuery, query, runGeneration]);

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value);
    if (validationError) setValidationError(null);
  }, [validationError]);

  const handleClear = useCallback(() => {
    setQuery('');
    setResult(null);
    setValidationError(null);
    setGenerationError(null);
    setLastQuery('');
  }, []);

  const showInitialState = !loading && !result && !generationError;

  return (
    <div className="space-y-5 p-6 lg:p-8">
      {/* ── Page header ── */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-600">
            <BrainCircuit className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold leading-tight tracking-tight">
              AI Insights
            </h1>
            <p className="txt-muted mt-0.5 text-[13px] font-medium">
              Turn CRM activity, pipeline signals and customer interactions into actionable sales intelligence.
            </p>
          </div>
        </div>
      </header>

      {/* ── Query workspace ── */}
      <AiQueryPanel
        query={query}
        onQueryChange={handleQueryChange}
        onGenerate={handleGenerate}
        onClear={handleClear}
        suggestedPrompts={SUGGESTED_PROMPTS}
        recentSearches={recentSearches}
        loading={loading}
        hasResult={result !== null || generationError !== null}
        error={validationError}
      />

      {/* ── Generated intelligence ── */}
      <div aria-live="polite" aria-busy={loading}>
        {loading && (
          <div className="space-y-3">
            <p className="txt-muted flex items-center gap-2 text-[13px] font-medium">
              <Sparkles className="h-4 w-4 motion-safe:animate-pulse" style={{ color: 'var(--accent)' }} aria-hidden="true" />
              Analysing CRM signals for &ldquo;{lastQuery}&rdquo;…
            </p>
            <AiInsightsSkeleton />
          </div>
        )}

        {!loading && generationError && (
          <div className="surface bd rounded-2xl border p-6">
            <AiEmptyState
              icon={AlertCircle}
              title="Insights could not be generated"
              description={generationError}
              action={
                <button
                  type="button"
                  onClick={handleRetry}
                  className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
                  style={{ background: 'var(--accent)' }}
                >
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  Retry
                </button>
              }
            />
          </div>
        )}

        {!loading && result?.status === 'no-match' && (
          <div className="surface bd rounded-2xl border p-6">
            <AiEmptyState
              icon={SearchX}
              title={`No CRM match for “${result.query}”`}
              description="Nothing in the current dataset matches that lead, company or opportunity. Try one of these instead:"
              action={
                <div className="flex flex-wrap justify-center gap-1.5">
                  {result.suggestions.map(suggestion => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => {
                        setQuery(suggestion);
                        void runGeneration(suggestion);
                      }}
                      className="ctl txt-muted rounded-full px-3 py-1.5 text-[12px] font-medium transition hover:border-[var(--accent)] hover:opacity-90"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              }
            />
          </div>
        )}

        {!loading && result?.status === 'resolved' && (
          <div className="space-y-4">
            <AiExecutiveSummary report={result.report} focusNote={result.focusNote} />
            <AiInsightsReport report={result.report} />
          </div>
        )}

        {showInitialState && (
          <div className="surface bd rounded-2xl border p-6 sm:p-8">
            <div className="mx-auto max-w-3xl text-center">
              <div
                className="mx-auto grid h-12 w-12 place-items-center rounded-2xl"
                style={{ background: 'var(--accent-soft)' }}
              >
                <Sparkles className="h-6 w-6" style={{ color: 'var(--accent)' }} aria-hidden="true" />
              </div>
              <h2 className="font-display txt mt-3 text-[17px] font-extrabold">
                Ask about any account, deal or pipeline question
              </h2>
              <p className="txt-muted mx-auto mt-1.5 max-w-xl text-[13px] leading-relaxed">
                Search a lead, company or opportunity — or start from a suggested prompt above.
                Generated intelligence covers the areas below.
              </p>
            </div>

            <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {ANALYSIS_CAPABILITIES.map(capability => (
                <li key={capability.title} className="surface-2 bd rounded-xl border p-3.5">
                  <p className="txt text-[13px] font-semibold">{capability.title}</p>
                  <p className="txt-muted mt-0.5 text-[12px] leading-relaxed">
                    {capability.description}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* ── Portfolio analytics ── */}
      <div className="bd border-t pt-5">
        <SalesIntelligenceSnapshot data={snapshot} />
      </div>
    </div>
  );
}
