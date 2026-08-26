// features/crm/pipeline-journey — API access
//
// Pipeline Journey owns no endpoint of its own. It composes three reads that
// already exist:
//
//   /crm/dashboard/summary    open pipeline stages with counts and values
//   /crm/opportunities/stages stage definitions, incl. win probability
//   /crm/leads                the top of the funnel, for its total only
//
// Composing rather than adding an endpoint is deliberate: every figure the
// page shows is then the *same* figure the dashboard and the list pages show,
// resolved by the same permission and visibility rules. A dedicated
// aggregate would be a second opinion about the same rows, and the first time
// the two disagreed the page would be lying about one of them.
//
// What this cannot supply is documented in `use-journey-data.ts`. Those
// figures are reported as unavailable rather than estimated.

import { apiRequest } from '@/lib/api-client';
import type { DashboardSummary } from '@/features/crm/dashboard/types';

/** One stage of the organization's pipeline (`PipelineStageResponse`). */
export interface PipelineStage {
  id: string;
  pipeline_id: string;
  name: string;
  sort_order: number;
  /** 0–100, or null when the stage carries no default. Drives the forecast. */
  default_probability: number | null;
  is_won: boolean;
  is_lost: boolean;
}

/**
 * The standard list envelope.
 *
 * The total lives under `pagination`, not at the top level — reading
 * `page.total` yields `undefined`, which then renders as "undefined
 * opportunities" rather than failing loudly.
 */
interface Page<T> {
  data: T[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
    has_more: boolean;
  };
}

export function fetchStages(signal?: AbortSignal): Promise<PipelineStage[]> {
  return apiRequest<PipelineStage[]>('/crm/opportunities/stages', {
    method: 'GET',
    signal,
  });
}

export function fetchDashboard(signal?: AbortSignal): Promise<DashboardSummary> {
  return apiRequest<DashboardSummary>('/crm/dashboard/summary', {
    method: 'GET',
    signal,
  });
}

/**
 * How many leads exist, without transferring any of them.
 *
 * `limit=1` because only the envelope's `total` is wanted — the funnel's top
 * row is a count, and paging the whole table to derive it would be the most
 * expensive query on the page by a wide margin.
 */
export async function fetchLeadTotal(signal?: AbortSignal): Promise<number> {
  const page = await apiRequest<Page<unknown>>('/crm/leads?page_size=1', {
    method: 'GET',
    signal,
  });
  return page.pagination.total;
}

/** Open opportunities in one stage, for the drawer. */
export function fetchStageDeals(
  stageId: string,
  limit: number,
  signal?: AbortSignal,
): Promise<Page<StageDeal>> {
  const query = new URLSearchParams({
    stage_id: stageId,
    is_open: 'true',
    page_size: String(limit),
  });
  return apiRequest<Page<StageDeal>>(`/crm/opportunities?${query.toString()}`, {
    method: 'GET',
    signal,
  });
}

/** The subset of `OpportunityResponse` the drawer renders. */
export interface StageDeal {
  id: string;
  name: string;
  account_id: string;
  deal_value: string | null;
  currency: string;
  win_probability: number | null;
  expected_close_date: string | null;
  owner_id: string | null;
  updated_at: string;
}
