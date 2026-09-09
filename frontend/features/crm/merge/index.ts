/**
 * Record merge — types and API access.
 *
 * Mirrors `backend/app/products/crm/merge/schemas.py`.
 *
 * **`field_choices` names a source, never a value**, and that is a security
 * property rather than a style choice: a client that could post *values* could
 * write anything into the surviving record under the guise of a merge,
 * bypassing every rule that record's own PATCH endpoint enforces. Naming a
 * source means the result can only ever be a value already in one of the
 * records being merged.
 *
 * Preview and merge are separate calls on purpose. Preview reads and locks
 * nothing, so its answer can be stale by the time the merge runs — the merge
 * re-reads under a row lock rather than trusting it.
 */

import { api } from '@/lib/api-client';

/** The record types a merge is offered for. */
export type MergeEntity = 'accounts' | 'contacts' | 'leads';

export const MERGE_ENTITIES: MergeEntity[] = ['accounts', 'contacts', 'leads'];

/** `"primary"` or a duplicate's id. */
export const KEEP_PRIMARY = 'primary';

export interface MergeConflict {
  field: string;
  /** Every record's value, keyed by record id — the survivor included. */
  values: Record<string, unknown>;
  /** What the field becomes if nothing is chosen. */
  default: unknown;
}

export interface MergePreview {
  primary_id: string;
  duplicate_ids: string[];
  conflicts: MergeConflict[];
  /** How much would move, e.g. `{ activities: 12, notes: 3 }`. */
  related_counts: Record<string, number>;
}

export interface MergeResult {
  id: string;
  entity_type: string;
  merged_ids: string[];
}

export interface MergeRequest {
  primary_id: string;
  duplicate_ids: string[];
  /** `{ field: "primary" | "<duplicate id>" }`. Omitted fields keep the survivor's value. */
  field_choices?: Record<string, string>;
}

/** What a merge would change. Needs only VIEW; changes nothing. */
export const previewMerge = (entity: MergeEntity, body: Omit<MergeRequest, 'field_choices'>) =>
  api.post<MergePreview>(`/crm/merge/${entity}/preview`, body);

/**
 * Perform the merge. Needs EDIT **and** DELETE on the record's module.
 *
 * Everything happens in one transaction: references move, then the duplicates
 * are retired pointing at the survivor. A failure leaves nothing moved.
 */
export const mergeRecords = (entity: MergeEntity, body: MergeRequest) =>
  api.post<MergeResult>(`/crm/merge/${entity}`, body);

/**
 * A stored value as a person should read it, for the conflict table.
 *
 * Deliberately plain: this renders values from an arbitrary column of an
 * arbitrary record type, so there is no per-field formatter to reach for and
 * inventing one would misrepresent as often as it helped.
 */
export function describeMergeValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.length ? value.map(String).join(', ') : '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** A column name as a heading: `company_size` → `Company size`. */
export function humanizeField(field: string): string {
  const words = field.replace(/_id$/, '').split('_');
  const [first, ...rest] = words;
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(' ');
}
