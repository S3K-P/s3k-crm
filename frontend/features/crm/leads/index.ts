/**
 * Leads — types and API access.
 *
 * Mirrors `backend/app/products/crm/leads/schemas.py`. Status changes and
 * conversion have their own endpoints because both carry rules the backend
 * enforces: illegal transitions are rejected, and conversion is transactional.
 */

import { api } from '@/lib/api-client';
import { downloadAndSave } from '@/lib/save-file';
import { toQuery, withoutPaging, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export type LeadStatus =
  | 'NEW'
  | 'CONTACTED'
  | 'QUALIFIED'
  | 'PROPOSAL_SENT'
  | 'NEGOTIATION'
  | 'UNQUALIFIED'
  | 'CONVERTED'
  | 'LOST';

export type Priority = 'HIGH' | 'MEDIUM' | 'LOW';

/** Board columns, in pipeline order. Terminal states are shown last. */
export const LEAD_STATUSES: LeadStatus[] = [
  'NEW',
  'CONTACTED',
  'QUALIFIED',
  'PROPOSAL_SENT',
  'NEGOTIATION',
  'UNQUALIFIED',
  'CONVERTED',
  'LOST',
];

export const PRIORITIES: Priority[] = ['HIGH', 'MEDIUM', 'LOW'];

export interface Lead extends RecordMeta {
  first_name: string;
  last_name: string;
  company: string | null;
  email: string | null;
  phone: string | null;
  status: LeadStatus;
  priority: Priority | null;
  owner_id: string | null;
  lead_source_id: string | null;
  campaign_id: string | null;
  industry: string | null;
  website: string | null;
  company_size: string | null;
  product_interest: string | null;
  expected_deal_size: string | null;
  ai_score: number | null;
  notes: string | null;
  lost_reason: string | null;
  converted_at: string | null;
  converted_account_id: string | null;
  converted_contact_id: string | null;
  converted_opportunity_id: string | null;
}

export interface LeadInput {
  first_name: string;
  last_name: string;
  company?: string | null;
  email?: string | null;
  phone?: string | null;
  priority?: Priority;
  owner_id?: string | null;
  lead_source_id?: string | null;
  industry?: string | null;
  website?: string | null;
  company_size?: string | null;
  product_interest?: string | null;
  expected_deal_size?: string | null;
  notes?: string | null;
  /**
   * Marketing attribution. Accepted by `LeadCreate` but **not** by
   * `LeadUpdate`, so it can only be set when the lead is created — sending it
   * on a PATCH is silently ignored by the backend.
   */
  campaign_id?: string | null;
}

export interface LeadListParams extends ListParams {
  status?: LeadStatus | null;
  owner_id?: string | null;
  lead_source_id?: string | null;
}

export interface LeadStatusCounts {
  counts: Record<string, number>;
}

export interface LeadConversionResult {
  lead_id: string;
  account_id: string;
  contact_id: string;
  opportunity_id: string | null;
}

export interface ConversionMatchAccount {
  id: string;
  name: string;
}

export interface ConversionMatchContact {
  id: string;
  full_name: string;
  email: string | null;
  account_id: string | null;
}

/** Existing records the convert UI should offer to link instead of recreate. */
export interface LeadConversionSuggestions {
  matching_accounts: ConversionMatchAccount[];
  matching_contacts: ConversionMatchContact[];
  suggested_account_name: string;
  suggested_contact_name: string;
  suggested_opportunity_name: string;
  suggested_deal_value: string | null;
}

export const listLeads = (params?: LeadListParams) =>
  api.get<Page<Lead>>(`/crm/leads${toQuery(params)}`);

/**
 * Download the leads matching `params` as CSV.
 *
 * Takes the same parameters as `listLeads` so the file matches the screen —
 * the backend applies the identical filters and the identical record-level
 * visibility, and pagination is deliberately not passed: an export is the
 * whole filtered set, not the page being looked at.
 *
 * Requires the `leads.EXPORT` permission; the API answers 403 without it,
 * and 413 when the filtered set is larger than the export ceiling.
 */
export const exportLeads = (params?: LeadListParams) =>
  downloadAndSave(`/crm/leads/export${toQuery(withoutPaging(params))}`, 'leads.csv');

export const getLead = (id: string) => api.get<Lead>(`/crm/leads/${id}`);

export const leadStatusCounts = () =>
  api.get<LeadStatusCounts>('/crm/leads/status-counts');

/** `allowDuplicate` re-submits past the duplicate-email warning. */
export const createLead = (body: LeadInput, allowDuplicate = false) =>
  api.post<Lead>(`/crm/leads${allowDuplicate ? '?allow_duplicate=true' : ''}`, body);

export const updateLead = (id: string, body: Partial<LeadInput>) =>
  api.patch<Lead>(`/crm/leads/${id}`, body);

/** Illegal transitions return 422 with the allowed set in `details`. */
export const changeLeadStatus = (id: string, status: LeadStatus, lostReason?: string) =>
  api.post<Lead>(`/crm/leads/${id}/status`, { status, lost_reason: lostReason ?? null });

export const assignLeadOwner = (id: string, ownerId: string | null) =>
  api.post<Lead>(`/crm/leads/${id}/owner`, { owner_id: ownerId });

export const getLeadConversionSuggestions = (id: string) =>
  api.get<LeadConversionSuggestions>(`/crm/leads/${id}/conversion-suggestions`);

export const convertLead = (
  id: string,
  body: {
    account_id?: string | null;
    contact_id?: string | null;
    create_opportunity?: boolean;
    opportunity_name?: string | null;
    opportunity_value?: string | null;
    /** Opening stage for the new deal. Omitted, the backend picks the first. */
    stage_id?: string | null;
    expected_close_date?: string | null;
  },
) => api.post<LeadConversionResult>(`/crm/leads/${id}/convert`, body);

export const archiveLead = (id: string) => api.delete<void>(`/crm/leads/${id}`);
