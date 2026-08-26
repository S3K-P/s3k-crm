/**
 * Lead sources — types and API access.
 *
 * Mirrors the `LeadSource*` schemas in
 * `backend/app/products/crm/leads/schemas.py`. `lead_count` is derived by the
 * backend per request, so it always agrees with the leads table.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export type LeadSourceStatus = 'ACTIVE' | 'INACTIVE';

export const LEAD_SOURCE_STATUSES: LeadSourceStatus[] = ['ACTIVE', 'INACTIVE'];

export interface LeadSource extends RecordMeta {
  name: string;
  category: string | null;
  description: string | null;
  status: LeadSourceStatus;
  lead_count: number;
}

export interface LeadSourceInput {
  name: string;
  category?: string | null;
  description?: string | null;
  status?: LeadSourceStatus;
}

export interface LeadSourceListParams extends ListParams {
  status?: LeadSourceStatus | null;
  category?: string | null;
}

export const listLeadSources = (params?: LeadSourceListParams) =>
  api.get<Page<LeadSource>>(`/crm/lead-sources${toQuery(params)}`);

export const getLeadSource = (id: string) => api.get<LeadSource>(`/crm/lead-sources/${id}`);

export const createLeadSource = (body: LeadSourceInput) =>
  api.post<LeadSource>('/crm/lead-sources', body);

export const updateLeadSource = (id: string, body: Partial<LeadSourceInput>) =>
  api.patch<LeadSource>(`/crm/lead-sources/${id}`, body);

/** Returns 409 while leads still reference the source — deactivate instead. */
export const archiveLeadSource = (id: string) =>
  api.delete<void>(`/crm/lead-sources/${id}`);
