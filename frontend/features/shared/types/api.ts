/**
 * Shapes the backend uses for every list endpoint.
 *
 * Mirrors `app/products/crm/shared/pagination.py`. Hand-written rather than
 * generated: the plan calls for an `orval` client (P0-W03-FE-01) which does not
 * exist yet, so this file is the single place the envelope is described and the
 * one place to change when it is generated for real.
 */

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_more: boolean;
}

export interface Page<T> {
  data: T[];
  pagination: PageMeta;
}

/** Query parameters every list endpoint accepts. */
export interface ListParams {
  page?: number;
  page_size?: number;
  sort_by?: string | null;
  sort_dir?: 'asc' | 'desc';
  search?: string | null;
  [key: string]: string | number | boolean | null | undefined;
}

/**
 * The same filters, without the page the user happens to be looking at.
 *
 * An export is the whole filtered set, so passing `page`/`page_size` through
 * would either be ignored or — worse, if the endpoint ever grew them — quietly
 * truncate the file to 25 rows.
 *
 * Stripping them here rather than typing the export parameter as
 * `Omit<XListParams, 'page' | 'page_size'>` is deliberate. `ListParams` carries
 * an index signature, and `Omit` over such a type collapses every declared key
 * into it: the result accepts `status: 'anything'` where the list function
 * demands one of four literals. Keeping the parameter type intact keeps that
 * check.
 */
export function withoutPaging<T extends ListParams>(params: T | undefined): ListParams | undefined {
  if (!params) return undefined;
  const filters: ListParams = {};
  for (const [key, value] of Object.entries(params)) {
    if (key === 'page' || key === 'page_size') continue;
    filters[key] = value;
  }
  return filters;
}

/** Drop empty values so the query string carries only real filters. */
export function toQuery(params: ListParams | undefined): string {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

/** An audit-column set every CRM record carries. */
export interface RecordMeta {
  id: string;
  organization_id: string;
  created_at: string;
  updated_at: string;
  created_by_id: string | null;
  updated_by_id: string | null;
}
