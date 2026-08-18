/**
 * Leads — types and API access.
 *
 * Mirrors `backend/app/products/crm/leads/schemas.py`. Status changes and
 * conversion have their own endpoints because both carry rules the backend
 * enforces: illegal transitions are rejected, and conversion is transactional.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export type LeadStatus =
  | 'NEW'
  | 'CONTACTED'
  | 'QUALIFIED'
  | 'PROPOSAL_SENT'
  | 'NEGOTIATION'
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
  expected_deal_size?: string | null;
  notes?: string | null;
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

export const listLeads = (params?: LeadListParams) =>
  api.get<Page<Lead>>(`/crm/leads${toQuery(params)}`);

export const getLead = (id: string) => api.get<Lead>(`/crm/leads/${id}`);

export const leadStatusCounts = () =>
  api.get<LeadStatusCounts>('/crm/leads/status-counts');

export const createLead = (body: LeadInput) => api.post<Lead>('/crm/leads', body);

export const updateLead = (id: string, body: Partial<LeadInput>) =>
  api.patch<Lead>(`/crm/leads/${id}`, body);

/** Illegal transitions return 422 with the allowed set in `details`. */
export const changeLeadStatus = (id: string, status: LeadStatus, lostReason?: string) =>
  api.post<Lead>(`/crm/leads/${id}/status`, { status, lost_reason: lostReason ?? null });

export const assignLeadOwner = (id: string, ownerId: string | null) =>
  api.post<Lead>(`/crm/leads/${id}/owner`, { owner_id: ownerId });

export const convertLead = (
  id: string,
  body: {
    account_id?: string | null;
    create_opportunity?: boolean;
    opportunity_name?: string | null;
    opportunity_value?: string | null;
    expected_close_date?: string | null;
  },
) => api.post<LeadConversionResult>(`/crm/leads/${id}/convert`, body);

export const archiveLead = (id: string) => api.delete<void>(`/crm/leads/${id}`);
