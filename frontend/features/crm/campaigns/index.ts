/**
 * Campaigns — types and API access.
 *
 * Mirrors `backend/app/products/crm/campaigns/schemas.py`.
 *
 * `leads_generated`, `opportunities_generated`, `conversion_rate` and `roi`
 * are **read-only**: the backend owns them and rejects them on write. They are
 * currently whatever the campaign service has computed, not client input — the
 * scheduled recomputation job is P2-W15-BE-05 and does not exist yet, so a
 * freshly created campaign legitimately reports zero.
 *
 * `member_count` is derived per request from `campaign_members`, so it cannot
 * drift from the membership table.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export type CampaignType =
  | 'EMAIL'
  | 'WEBINAR'
  | 'SOCIAL_MEDIA'
  | 'EVENT'
  | 'ADVERTISEMENT';

export type CampaignStatus =
  | 'PLANNING'
  | 'ACTIVE'
  | 'PAUSED'
  | 'COMPLETED'
  | 'CANCELLED';

/** Who can be enrolled in a campaign. Mirrors `CampaignMemberType`. */
export type CampaignMemberType = 'LEAD' | 'CONTACT';

export const CAMPAIGN_TYPES: CampaignType[] = [
  'EMAIL',
  'WEBINAR',
  'SOCIAL_MEDIA',
  'EVENT',
  'ADVERTISEMENT',
];

export const CAMPAIGN_STATUSES: CampaignStatus[] = [
  'PLANNING',
  'ACTIVE',
  'PAUSED',
  'COMPLETED',
  'CANCELLED',
];

export const CAMPAIGN_MEMBER_TYPES: CampaignMemberType[] = ['LEAD', 'CONTACT'];

export interface Campaign extends RecordMeta {
  name: string;
  type: CampaignType;
  status: CampaignStatus;
  owner_id: string | null;
  start_date: string | null;
  end_date: string | null;
  budget: string | null;
  expected_revenue: string | null;
  target_audience: string | null;
  lead_source_id: string | null;
  products: string | null;
  notes: string | null;
  /* --- Backend-owned metrics. Never sent on create or update. --- */
  leads_generated: number;
  opportunities_generated: number;
  conversion_rate: string | null;
  roi: string | null;
  member_count: number;
}

export interface CampaignInput {
  name: string;
  type: CampaignType;
  status?: CampaignStatus;
  owner_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  budget?: string | null;
  expected_revenue?: string | null;
  target_audience?: string | null;
  lead_source_id?: string | null;
  products?: string | null;
  notes?: string | null;
}

export interface CampaignListParams extends ListParams {
  status?: CampaignStatus | null;
  type?: CampaignType | null;
  owner_id?: string | null;
}

export interface CampaignMember {
  id: string;
  campaign_id: string;
  entity_type: CampaignMemberType;
  entity_id: string;
  added_at: string;
}

export const listCampaigns = (params?: CampaignListParams) =>
  api.get<Page<Campaign>>(`/crm/campaigns${toQuery(params)}`);

export const getCampaign = (id: string) => api.get<Campaign>(`/crm/campaigns/${id}`);

export const createCampaign = (body: CampaignInput) =>
  api.post<Campaign>('/crm/campaigns', body);

export const updateCampaign = (id: string, body: Partial<CampaignInput>) =>
  api.patch<Campaign>(`/crm/campaigns/${id}`, body);

export const archiveCampaign = (id: string) => api.delete<void>(`/crm/campaigns/${id}`);

/* ------------------------------------------------------------------
   Membership
   ------------------------------------------------------------------ */

export const listCampaignMembers = (campaignId: string) =>
  api.get<CampaignMember[]>(`/crm/campaigns/${campaignId}/members`);

/** Returns 409 if the record is already enrolled, 404 if it is not ours. */
export const addCampaignMember = (
  campaignId: string,
  body: { entity_type: CampaignMemberType; entity_id: string },
) => api.post<CampaignMember>(`/crm/campaigns/${campaignId}/members`, body);

export const removeCampaignMember = (campaignId: string, memberId: string) =>
  api.delete<void>(`/crm/campaigns/${campaignId}/members/${memberId}`);
