/**
 * Accounts — types and API access.
 *
 * Mirrors `backend/app/products/crm/accounts/schemas.py`. Every function here
 * hits the real API; there is no local fixture behind any of them.
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
  type TimelineEntryKind,
} from '@/features/shared/types/api';
import type { CustomFieldValues } from '@/features/crm/custom-fields';
import type { Rating } from '@/features/crm/leads';

export type { Rating };
export type AccountStatus = 'ACTIVE' | 'ONBOARDING' | 'AT_RISK' | 'CHURNED';

export const ACCOUNT_STATUSES: AccountStatus[] = [
  'ACTIVE',
  'ONBOARDING',
  'AT_RISK',
  'CHURNED',
];

export interface Account extends RecordMeta {
  name: string;
  account_type: string | null;
  industry: string | null;
  website: string | null;
  phone: string | null;
  fax: string | null;
  email: string | null;
  rating: Rating | null;
  company_size: string | null;
  annual_revenue: string | null;
  parent_account_id: string | null;
  status: AccountStatus;
  owner_id: string | null;
  primary_contact_id: string | null;
  health_score: number | null;
  source: string | null;
  description: string | null;
  address_line1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  shipping_address_line1: string | null;
  shipping_city: string | null;
  shipping_state: string | null;
  shipping_postal_code: string | null;
  shipping_country: string | null;
  /**
   * Tenant-defined values, keyed by `api_name`. Always present — the column is
   * `NOT NULL DEFAULT '{}'` — so this is `{}` rather than absent for a record
   * whose organization has defined no fields.
   */
  custom_fields: CustomFieldValues;
}

export interface AccountInput {
  name: string;
  account_type?: string | null;
  industry?: string | null;
  website?: string | null;
  phone?: string | null;
  fax?: string | null;
  email?: string | null;
  rating?: Rating | null;
  company_size?: string | null;
  annual_revenue?: string | null;
  parent_account_id?: string | null;
  status?: AccountStatus;
  owner_id?: string | null;
  health_score?: number | null;
  source?: string | null;
  description?: string | null;
  address_line1?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  shipping_address_line1?: string | null;
  shipping_city?: string | null;
  shipping_state?: string | null;
  shipping_postal_code?: string | null;
  shipping_country?: string | null;
  /**
   * Tenant-defined values. Omit the key entirely to leave the record's existing
   * document untouched; `{}` clears it. The two are different on the wire, so
   * never spread a default `{}` into a patch.
   */
  custom_fields?: CustomFieldValues;
}

export interface AccountListParams extends ListParams {
  status?: AccountStatus | null;
  industry?: string | null;
  owner_id?: string | null;
}

export const listAccounts = (params?: AccountListParams) =>
  api.get<Page<Account>>(`/crm/accounts${toQuery(params)}`);

/**
 * Download the accounts matching `params` as CSV.
 *
 * Takes the same parameters as `listAccounts` so the file matches the screen —
 * the backend applies the identical filters and the identical record-level
 * visibility, and pagination is deliberately not passed: an export is the
 * whole filtered set, not the page being looked at.
 *
 * Requires the `accounts.EXPORT` permission; the API answers 403 without it,
 * and 413 when the filtered set is larger than the export ceiling.
 */
export const exportAccounts = (params?: AccountListParams) =>
  downloadAndSave(`/crm/accounts/export${toQuery(withoutPaging(params))}`, 'accounts.csv');

export const getAccount = (id: string) => api.get<Account>(`/crm/accounts/${id}`);

/** `allowDuplicate` re-submits past the duplicate-name warning (decision C03). */
export const createAccount = (body: AccountInput, allowDuplicate = false) =>
  api.post<Account>(`/crm/accounts${allowDuplicate ? '?allow_duplicate=true' : ''}`, body);

export const updateAccount = (id: string, body: Partial<AccountInput>) =>
  api.patch<Account>(`/crm/accounts/${id}`, body);

export const archiveAccount = (id: string) => api.delete<void>(`/crm/accounts/${id}`);

/** Each id is validated and saved independently — see `features/crm/leads`. */
export const bulkUpdateAccounts = (ids: string[], values: Partial<AccountInput>) =>
  api.post<BulkOperationResult>('/crm/accounts/bulk-update', { ids, values });

export const bulkDeleteAccounts = (ids: string[]) =>
  api.post<BulkOperationResult>('/crm/accounts/bulk-delete', { ids });

/* ------------------------------------------------------------------
   Account 360: the summary header and the unified timeline
   ------------------------------------------------------------------ */

export interface AccountOverview {
  contacts_count: number;
  open_deals_count: number;
  open_pipeline_value: string;
  /** Set only when every open deal shares one currency. */
  open_pipeline_currency: string | null;
  won_deals_count: number;
  won_revenue: string;
  won_revenue_currency: string | null;
  open_tasks_count: number;
  last_activity_at: string | null;
  next_meeting_id: string | null;
  next_meeting_title: string | null;
  next_meeting_at: string | null;
  owner_name: string | null;
  primary_contact_name: string | null;
  primary_contact_title: string | null;
}

export const getAccountOverview = (id: string) =>
  api.get<AccountOverview>(`/crm/accounts/${id}/overview`);

/** See `backend/app/products/crm/shared/timeline.py` for the full vocabulary. */
export type AccountTimelineEntryKind = TimelineEntryKind;
export type AccountTimelineEntry = TimelineEntry;

export const getAccountTimeline = (id: string, limit = 50) =>
  api.get<AccountTimelineEntry[]>(`/crm/accounts/${id}/timeline?limit=${limit}`);
