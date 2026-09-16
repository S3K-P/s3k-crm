/**
 * Opportunities — types and API access.
 *
 * Mirrors `backend/app/products/crm/opportunities/schemas.py`. Stage movement
 * has its own endpoint because the backend records history and enforces the
 * win/loss rules on that path; a plain PATCH deliberately ignores `stage_id`.
 */

import { api } from '@/lib/api-client';
import { downloadAndSave } from '@/lib/save-file';
import {
  toQuery,
  withoutPaging,
  type BulkOperationResult,
  type ListParams,
  type Page,
  type RecordMeta,
  type TimelineEntry,
} from '@/features/shared/types/api';
import type { CustomFieldValues } from '@/features/crm/custom-fields';

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
  /**
   * Tenant-defined values, keyed by `api_name`. Always present — the column is
   * `NOT NULL DEFAULT '{}'` — so this is `{}` rather than absent for a record
   * whose organization has defined no fields.
   */
  custom_fields: CustomFieldValues;
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
  /**
   * Tenant-defined values. Omit the key entirely to leave the record's existing
   * document untouched; `{}` clears it. The two are different on the wire, so
   * never spread a default `{}` into a patch.
   */
  custom_fields?: CustomFieldValues;
}

export interface OpportunityListParams extends ListParams {
  stage_id?: string | null;
  account_id?: string | null;
  primary_contact_id?: string | null;
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

/**
 * Download the opportunities matching `params` as CSV.
 *
 * Takes the same parameters as `listOpportunities` so the file matches the screen —
 * the backend applies the identical filters and the identical record-level
 * visibility, and pagination is deliberately not passed: an export is the
 * whole filtered set, not the page being looked at.
 *
 * Requires the `opportunities.EXPORT` permission; the API answers 403 without it,
 * and 413 when the filtered set is larger than the export ceiling.
 */
export const exportOpportunities = (params?: OpportunityListParams) =>
  downloadAndSave(`/crm/opportunities/export${toQuery(withoutPaging(params))}`, 'opportunities.csv');

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

/** Every event this caller may see against this deal, newest first. */
export const getOpportunityTimeline = (id: string, limit = 50) =>
  api.get<TimelineEntry[]>(`/crm/opportunities/${id}/timeline?limit=${limit}`);

/* ------------------------------------------------------------------
   Bulk operations (Checkpoint 4) — see `features/crm/leads`'s own
   section for the shared reasoning: each call is many single-record
   writes, not one blanket UPDATE. Unlike `LeadInput`, `OpportunityInput`
   still carries `stage_id` (it is shared between create and update on this
   side), so the *frontend* type alone does not rule it out of a bulk edit —
   the caller (the bulk-edit field picker) simply never offers it. The
   guarantee that actually holds regardless is the backend's: `PATCH
   .../bulk-update` validates against `OpportunityUpdate`, which has no
   `stage_id` field at all, so a value sent anyway is dropped before it
   reaches a row. A bulk stage move instead runs every deal through the
   identical `changeStage` rules — closed-deal refusal, the missing-reason
   check, blueprint validation.
   ------------------------------------------------------------------ */

export const bulkUpdateOpportunities = (ids: string[], values: Partial<OpportunityInput>) =>
  api.post<BulkOperationResult>('/crm/opportunities/bulk-update', { ids, values });

export const bulkDeleteOpportunities = (ids: string[]) =>
  api.post<BulkOperationResult>('/crm/opportunities/bulk-delete', { ids });

export const bulkChangeStage = (
  ids: string[],
  body: { stage_id: string; note?: string | null; loss_reason?: string | null; win_reason?: string | null },
) => api.post<BulkOperationResult>('/crm/opportunities/bulk-stage', { ids, ...body });
