/**
 * Accounts — types and API access.
 *
 * Mirrors `backend/app/products/crm/accounts/schemas.py`. Every function here
 * hits the real API; there is no local fixture behind any of them.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export type AccountStatus = 'ACTIVE' | 'ONBOARDING' | 'AT_RISK' | 'CHURNED';

export const ACCOUNT_STATUSES: AccountStatus[] = [
  'ACTIVE',
  'ONBOARDING',
  'AT_RISK',
  'CHURNED',
];

export interface Account extends RecordMeta {
  name: string;
  industry: string | null;
  website: string | null;
  company_size: string | null;
  annual_revenue: string | null;
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
}

export interface AccountInput {
  name: string;
  industry?: string | null;
  website?: string | null;
  company_size?: string | null;
  annual_revenue?: string | null;
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
}

export interface AccountListParams extends ListParams {
  status?: AccountStatus | null;
  industry?: string | null;
  owner_id?: string | null;
}

export const listAccounts = (params?: AccountListParams) =>
  api.get<Page<Account>>(`/crm/accounts${toQuery(params)}`);

export const getAccount = (id: string) => api.get<Account>(`/crm/accounts/${id}`);

/** `allowDuplicate` re-submits past the duplicate-name warning (decision C03). */
export const createAccount = (body: AccountInput, allowDuplicate = false) =>
  api.post<Account>(`/crm/accounts${allowDuplicate ? '?allow_duplicate=true' : ''}`, body);

export const updateAccount = (id: string, body: Partial<AccountInput>) =>
  api.patch<Account>(`/crm/accounts/${id}`, body);

export const archiveAccount = (id: string) => api.delete<void>(`/crm/accounts/${id}`);
