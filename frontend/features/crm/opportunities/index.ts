/**
 * Opportunities — types and API access.
 *
 * Mirrors `backend/app/products/crm/opportunities/schemas.py`. Stage movement
 * has its own endpoint because the backend records history and enforces the
 * win/loss rules on that path; a plain PATCH deliberately ignores `stage_id`.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export interface PipelineStage {
  id: string;
  pipeline_id: string;
  name: string;
  sort_order: number;
  default_probability: number | null;
  is_won: boolean;
  is_lost: boolean;
}

export interface Opportunity extends RecordMeta {
  name: string;
  account_id: string;
  primary_contact_id: string | null;
  owner_id: string | null;
  stage_id: string;
  deal_value: string | null;
  currency: string;
  win_probability: number | null;
  expected_close_date: string | null;
  health_score: number | null;
  forecast_category: string | null;
  competitor: string | null;
  lead_source_id: string | null;
  products: string | null;
  notes: string | null;
  won_at: string | null;
  lost_at: string | null;
  loss_reason: string | null;
  win_reason: string | null;
}

export interface OpportunityInput {
  name: string;
  account_id: string;
  stage_id?: string;
  primary_contact_id?: string | null;
  owner_id?: string | null;
  deal_value?: string | null;
  currency?: string;
  expected_close_date?: string | null;
  forecast_category?: string | null;
  competitor?: string | null;
  products?: string | null;
  notes?: string | null;
}

export interface OpportunityListParams extends ListParams {
  stage_id?: string | null;
  account_id?: string | null;
  owner_id?: string | null;
  is_open?: boolean | null;
}

export interface StageHistoryEntry {
  id: string;
  opportunity_id: string;
  from_stage_id: string | null;
  to_stage_id: string;
  changed_by_id: string | null;
  changed_at: string;
  note: string | null;
}

/** An opportunity is closed once either terminal timestamp is set. */
export const isClosed = (opportunity: Opportunity): boolean =>
  opportunity.won_at !== null || opportunity.lost_at !== null;

export const listOpportunities = (params?: OpportunityListParams) =>
  api.get<Page<Opportunity>>(`/crm/opportunities${toQuery(params)}`);

export const getOpportunity = (id: string) =>
  api.get<Opportunity>(`/crm/opportunities/${id}`);

export const listStages = () => api.get<PipelineStage[]>('/crm/opportunities/stages');

export const createOpportunity = (body: OpportunityInput) =>
  api.post<Opportunity>('/crm/opportunities', body);

export const updateOpportunity = (id: string, body: Partial<OpportunityInput>) =>
  api.patch<Opportunity>(`/crm/opportunities/${id}`, body);

/**
 * Move a deal to another stage.
 *
 * A stage flagged `is_lost` requires `loss_reason`; the backend returns 422
 * without one. A closed deal must be reopened before it can move again.
 */
export const changeStage = (
  id: string,
  body: { stage_id: string; note?: string | null; loss_reason?: string | null; win_reason?: string | null },
) => api.post<Opportunity>(`/crm/opportunities/${id}/stage`, body);

export const reopenOpportunity = (id: string, stageId: string) =>
  api.post<Opportunity>(`/crm/opportunities/${id}/reopen`, { stage_id: stageId });

export const stageHistory = (id: string) =>
  api.get<StageHistoryEntry[]>(`/crm/opportunities/${id}/history`);

export const archiveOpportunity = (id: string) =>
  api.delete<void>(`/crm/opportunities/${id}`);
