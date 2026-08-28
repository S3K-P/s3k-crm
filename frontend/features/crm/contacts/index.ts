/**
 * Contacts — types and API access.
 *
 * Mirrors `backend/app/products/crm/contacts/schemas.py`.
 */

import { api } from '@/lib/api-client';
import { downloadAndSave } from '@/lib/save-file';
import { toQuery, withoutPaging, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export type ContactStatus = 'ACTIVE' | 'INACTIVE';

export const CONTACT_STATUSES: ContactStatus[] = ['ACTIVE', 'INACTIVE'];

export interface Contact extends RecordMeta {
  account_id: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  mobile: string | null;
  job_title: string | null;
  department: string | null;
  owner_id: string | null;
  status: ContactStatus;
  ai_score: number | null;
  preferred_communication: string | null;
  linkedin_url: string | null;
  notes: string | null;
  address_line1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
}

export interface ContactInput {
  first_name: string;
  last_name: string;
  account_id?: string | null;
  email?: string | null;
  phone?: string | null;
  mobile?: string | null;
  job_title?: string | null;
  department?: string | null;
  owner_id?: string | null;
  status?: ContactStatus;
  linkedin_url?: string | null;
  notes?: string | null;
  address_line1?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  is_primary?: boolean;
}

export interface ContactListParams extends ListParams {
  status?: ContactStatus | null;
  account_id?: string | null;
  owner_id?: string | null;
}

export const listContacts = (params?: ContactListParams) =>
  api.get<Page<Contact>>(`/crm/contacts${toQuery(params)}`);

/**
 * Download the contacts matching `params` as CSV.
 *
 * Takes the same parameters as `listContacts` so the file matches the screen —
 * the backend applies the identical filters and the identical record-level
 * visibility, and pagination is deliberately not passed: an export is the
 * whole filtered set, not the page being looked at.
 *
 * Requires the `contacts.EXPORT` permission; the API answers 403 without it,
 * and 413 when the filtered set is larger than the export ceiling.
 */
export const exportContacts = (params?: ContactListParams) =>
  downloadAndSave(`/crm/contacts/export${toQuery(withoutPaging(params))}`, 'contacts.csv');

export const getContact = (id: string) => api.get<Contact>(`/crm/contacts/${id}`);

/** `allowDuplicate` re-submits past the duplicate-email warning. */
export const createContact = (body: ContactInput, allowDuplicate = false) =>
  api.post<Contact>(`/crm/contacts${allowDuplicate ? '?allow_duplicate=true' : ''}`, body);

export const updateContact = (
  id: string,
  body: Partial<ContactInput>,
  allowDuplicate = false,
) =>
  api.patch<Contact>(
    `/crm/contacts/${id}${allowDuplicate ? '?allow_duplicate=true' : ''}`,
    body,
  );

export const makeContactPrimary = (id: string) =>
  api.post<Contact>(`/crm/contacts/${id}/primary`);

export const archiveContact = (id: string) => api.delete<void>(`/crm/contacts/${id}`);
