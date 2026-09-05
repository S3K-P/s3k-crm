/**
 * The saved-report library — folders and saved reports.
 *
 * Mirrors `backend/app/products/crm/reports/{models,schemas}.py`. Kept beside
 * `index.ts` rather than inside it because the two answer different questions:
 * that module is about *running* a report and rendering the result, this one
 * is about the objects a user files and shares.
 */

import { api } from '@/lib/api-client';
import type { Page } from '@/features/shared/types/api';

import type { ReportResult } from '.';

/**
 * One page big enough to hold a realistic library.
 *
 * The sidebar shows folders and reports as a tree, which has no natural
 * "next page" affordance, so it asks for the maximum the API allows rather
 * than paginating something nobody would page through. Past 200 the tree is
 * the wrong UI and the fix is search, not a second request.
 */
const PAGE_SIZE = '200';

/** Mirrors the backend `ShareScope`. */
export type ShareScope = 'PRIVATE' | 'SHARED';

/** Mirrors the backend `ReportPeriod`. */
export type ReportPeriod =
  | 'ALL_TIME'
  | 'TODAY'
  | 'LAST_7_DAYS'
  | 'LAST_30_DAYS'
  | 'LAST_90_DAYS'
  | 'THIS_MONTH'
  | 'LAST_MONTH'
  | 'THIS_QUARTER'
  | 'LAST_QUARTER'
  | 'THIS_YEAR'
  | 'CUSTOM';

/**
 * Labels for the period picker, in the order they should appear.
 *
 * Ordered by how people reach for them — "all time" first because it is the
 * default and needs no thought, then trailing windows, then calendar ones —
 * rather than alphabetically, which would put "Last month" between "Last 90
 * days" and "Last quarter" and read as noise.
 */
export const REPORT_PERIODS: { value: ReportPeriod; label: string }[] = [
  { value: 'ALL_TIME', label: 'All time' },
  { value: 'TODAY', label: 'Today' },
  { value: 'LAST_7_DAYS', label: 'Last 7 days' },
  { value: 'LAST_30_DAYS', label: 'Last 30 days' },
  { value: 'LAST_90_DAYS', label: 'Last 90 days' },
  { value: 'THIS_MONTH', label: 'This month' },
  { value: 'LAST_MONTH', label: 'Last month' },
  { value: 'THIS_QUARTER', label: 'This quarter' },
  { value: 'LAST_QUARTER', label: 'Last quarter' },
  { value: 'THIS_YEAR', label: 'This year' },
  { value: 'CUSTOM', label: 'Custom range…' },
];

export const periodLabel = (period: ReportPeriod): string =>
  REPORT_PERIODS.find(entry => entry.value === period)?.label ?? period;

export interface ReportFolder {
  id: string;
  name: string;
  description: string | null;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedReport {
  id: string;
  name: string;
  description: string | null;
  base_report_key: string;
  folder_id: string | null;
  period: ReportPeriod;
  date_from: string | null;
  date_to: string | null;
  owner_id: string | null;
  visibility: ShareScope;
  created_at: string;
  updated_at: string;
}

export interface SavedReportInput {
  name: string;
  description?: string | null;
  base_report_key: string;
  folder_id?: string | null;
  period: ReportPeriod;
  date_from?: string | null;
  date_to?: string | null;
  visibility: ShareScope;
}

/* --- Folders --------------------------------------------------------- */

export const listFolders = () =>
  api.get<Page<ReportFolder>>(
    `/crm/reports/folders?page_size=${PAGE_SIZE}&sort_by=name&sort_dir=asc`,
  );

export const createFolder = (input: { name: string; description?: string | null }) =>
  api.post<ReportFolder>('/crm/reports/folders', input);

export const renameFolder = (id: string, input: { name?: string; description?: string | null }) =>
  api.patch<ReportFolder>(`/crm/reports/folders/${id}`, input);

export const deleteFolder = (id: string) => api.delete<void>(`/crm/reports/folders/${id}`);

/* --- Saved reports --------------------------------------------------- */

export const listSavedReports = (params: { folderId?: string; unfiled?: boolean } = {}) => {
  const query = new URLSearchParams({
    page_size: PAGE_SIZE,
    sort_by: 'name',
    sort_dir: 'asc',
  });
  if (params.unfiled) query.set('unfiled', 'true');
  else if (params.folderId) query.set('folder_id', params.folderId);
  return api.get<Page<SavedReport>>(`/crm/reports/saved?${query.toString()}`);
};

export const createSavedReport = (input: SavedReportInput) =>
  api.post<SavedReport>('/crm/reports/saved', input);

export const updateSavedReport = (id: string, input: Partial<SavedReportInput>) =>
  api.patch<SavedReport>(`/crm/reports/saved/${id}`, input);

export const deleteSavedReport = (id: string) => api.delete<void>(`/crm/reports/saved/${id}`);

export const runSavedReport = (id: string) =>
  api.post<ReportResult>(`/crm/reports/saved/${id}/run`, {});
