/**
 * Saved list views — types and API access.
 *
 * Mirrors `backend/app/products/crm/views/schemas.py`.
 *
 * A view stores a **question**, never an answer: filters, sort and columns, and
 * no rows. Two consequences worth holding on to when using this:
 *
 * 1. Opening a view means running the record type's own list endpoint with the
 *    saved filters. Nothing here fetches records, and a shared view shows each
 *    viewer only what their own permissions allow — so two colleagues opening
 *    one view legitimately see different rows.
 * 2. `can_edit` is computed per request for the caller who asked. Use it to
 *    hide controls, never to decide anything: the server refuses a write to
 *    somebody else's view whatever the client believed.
 */

import { api } from '@/lib/api-client';
import type { ListParams } from '@/features/shared/types/api';
import type { CustomFieldEntityType } from '@/features/crm/custom-fields';

/** Views exist for the same five record types custom fields do. */
export type ViewEntityType = CustomFieldEntityType;

export type ViewVisibility = 'PRIVATE' | 'TEAM' | 'ORGANIZATION';

export const VIEW_VISIBILITIES: ViewVisibility[] = ['PRIVATE', 'TEAM', 'ORGANIZATION'];

export const VISIBILITY_LABELS: Record<ViewVisibility, string> = {
  PRIVATE: 'Only me',
  TEAM: 'My team',
  ORGANIZATION: 'Everyone',
};

/**
 * A saved view's filters, in the list endpoint's own query vocabulary.
 *
 * Deliberately the same shape `ListParams` uses, including Phase E's `cf_*`
 * custom-field filters — a view is replayed by handing this straight to the
 * list call, so anything the screen can filter by, a view can save.
 */
export type ViewFilters = Record<string, string | number | boolean | null | (string | number)[]>;

export interface SavedView {
  id: string;
  entity_type: ViewEntityType;
  name: string;
  description: string | null;
  owner_id: string;
  visibility: ViewVisibility;
  filters: ViewFilters;
  columns: string[];
  sort_by: string | null;
  sort_dir: 'asc' | 'desc' | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  /** Whether *this* caller may change it. A hint for the UI, not the control. */
  can_edit: boolean;
}

export interface SavedViewInput {
  entity_type: ViewEntityType;
  name: string;
  description?: string | null;
  visibility?: ViewVisibility;
  filters?: ViewFilters;
  columns?: string[];
  sort_by?: string | null;
  sort_dir?: 'asc' | 'desc' | null;
  is_default?: boolean;
}

/**
 * A patch. `entity_type` is absent because the backend refuses it — a view
 * moved to another record type would have filters naming columns that entity
 * has not got.
 */
export type SavedViewPatch = Partial<Omit<SavedViewInput, 'entity_type'>>;

/** Views on one record type that the caller may read. Unpaginated by design. */
export const listViews = (entityType: ViewEntityType) =>
  api.get<SavedView[]>(`/crm/views?entity_type=${entityType}`);

export const getView = (id: string) => api.get<SavedView>(`/crm/views/${id}`);

export const createView = (body: SavedViewInput) => api.post<SavedView>('/crm/views', body);

export const updateView = (id: string, body: SavedViewPatch) =>
  api.patch<SavedView>(`/crm/views/${id}`, body);

/** Removes a saved question. No record is touched — a view holds none. */
export const deleteView = (id: string) => api.delete<void>(`/crm/views/${id}`);

/**
 * Turn a saved view into the parameters a list call takes.
 *
 * The one place a view becomes a request, so the rule that a view is *only*
 * filters lives here rather than being re-derived at each list screen.
 *
 * `page` is deliberately not carried: a view is a filter set, and reopening one
 * should start at the beginning rather than on whatever page its author
 * happened to be looking at when they saved it.
 */
export function viewToParams(view: SavedView): ListParams {
  const params: ListParams = { ...(view.filters as ListParams) };
  if (view.sort_by) params.sort_by = view.sort_by;
  if (view.sort_dir) params.sort_dir = view.sort_dir;
  return params;
}

/**
 * Whether a view's filters match what the screen is currently showing.
 *
 * Used to mark the active view in a picker. Compares serialised values rather
 * than identity because a filter that came back from the API as a number and
 * is held in the form as a string is the same filter to a user.
 */
export function matchesFilters(view: SavedView, current: ListParams): boolean {
  const saved = view.filters as Record<string, unknown>;
  const keys = new Set([...Object.keys(saved), ...Object.keys(current)]);
  for (const key of keys) {
    if (key === 'page' || key === 'page_size') continue;
    const a = normalise(saved[key]);
    const b = normalise((current as Record<string, unknown>)[key]);
    if (a !== b) return false;
  }
  return true;
}

function normalise(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (Array.isArray(value)) return value.map(String).sort().join(',');
  return String(value);
}
