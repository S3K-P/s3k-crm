import {
  INSIGHT_REPORTS,
  NO_MATCH_SUGGESTIONS,
  QUERY_ROUTES,
  buildSalesIntelligenceSnapshot,
} from './mock-data';
import type { AiInsightResult, SalesIntelligenceSnapshot } from './types';

/* ============================================================
   AI INSIGHTS — LOCAL GENERATION UTILITY

   Resolves a natural-language query against the local demo
   dataset. Everything runs in the browser: no fetch, no API
   route, no AI provider, no environment configuration.

   The delay exists only so the interface can demonstrate its
   skeleton loading state.
   ============================================================ */

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Resolves a query to one of the curated account intelligence reports.
 * Entity queries match directly; analytical queries ("which deals are at
 * risk?") resolve to the account that best represents the intent and
 * carry a note explaining the selection.
 */
export async function generateMockAIInsights(query: string): Promise<AiInsightResult> {
  const normalised = query.trim().toLowerCase();

  if (normalised.length === 0) {
    throw new Error('A query is required to generate insights');
  }

  await delay(1400);

  const route = QUERY_ROUTES.find(candidate =>
    candidate.keywords.some(keyword => normalised.includes(keyword)),
  );

  if (!route) {
    return { status: 'no-match', query: query.trim(), suggestions: NO_MATCH_SUGGESTIONS };
  }

  const report = INSIGHT_REPORTS.find(candidate => candidate.id === route.reportId);

  if (!report) {
    return { status: 'no-match', query: query.trim(), suggestions: NO_MATCH_SUGGESTIONS };
  }

  return { status: 'resolved', report, focusNote: route.focusNote };
}

/** Portfolio-level analytics shown beneath the generated insights. */
export function getSalesIntelligenceSnapshot(): SalesIntelligenceSnapshot {
  return buildSalesIntelligenceSnapshot();
}
