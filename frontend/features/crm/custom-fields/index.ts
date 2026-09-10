/**
 * Custom fields and picklists — types and API access.
 *
 * Mirrors `backend/app/products/crm/custom_fields/schemas.py`.
 *
 * Two things here are worth knowing before using them elsewhere:
 *
 * 1. **A record's `custom_fields` is `undefined` when it was not supplied and
 *    `{}` when it was cleared, and the two are different on the wire.** A PATCH
 *    that omits the key leaves the whole document alone; one that sends `{}`
 *    empties it. Never spread a default `{}` into a patch body.
 * 2. **Values are typed per definition, not per TypeScript.** The backend
 *    validates every one against the tenant's own field definitions, which are
 *    data. `CustomFieldValue` is therefore a union of the shapes the backend
 *    can store, and `describeValue` is the one place it is rendered.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

/** Record types that can carry tenant-defined fields. */
export type CustomFieldEntityType =
  | 'ACCOUNT'
  | 'CONTACT'
  | 'LEAD'
  | 'OPPORTUNITY'
  | 'CAMPAIGN';

export const CUSTOM_FIELD_ENTITY_TYPES: CustomFieldEntityType[] = [
  'ACCOUNT',
  'CONTACT',
  'LEAD',
  'OPPORTUNITY',
  'CAMPAIGN',
];

export type CustomFieldType =
  | 'TEXT'
  | 'TEXTAREA'
  | 'NUMBER'
  | 'DECIMAL'
  | 'DATE'
  | 'DATETIME'
  | 'BOOLEAN'
  | 'EMAIL'
  | 'URL'
  | 'PHONE'
  | 'PICKLIST'
  | 'MULTI_PICKLIST';

export const CUSTOM_FIELD_TYPES: CustomFieldType[] = [
  'TEXT',
  'TEXTAREA',
  'NUMBER',
  'DECIMAL',
  'DATE',
  'DATETIME',
  'BOOLEAN',
  'EMAIL',
  'URL',
  'PHONE',
  'PICKLIST',
  'MULTI_PICKLIST',
];

/** Types whose value is chosen from a picklist rather than typed. */
export const PICKLIST_TYPES: CustomFieldType[] = ['PICKLIST', 'MULTI_PICKLIST'];

export function isPicklistType(type: CustomFieldType): boolean {
  return PICKLIST_TYPES.includes(type);
}

export interface PicklistOption {
  id: string;
  picklist_id: string;
  value: string;
  label: string;
  position: number;
  is_active: boolean;
  is_default: boolean;
}

export interface Picklist extends RecordMeta {
  name: string;
  api_name: string;
  description: string | null;
  option_count: number;
  /** Present on the detail endpoint, absent from list rows. */
  options?: PicklistOption[] | null;
}

export interface CustomFieldDefinition {
  id: string;
  entity_type: CustomFieldEntityType;
  api_name: string;
  label: string;
  field_type: CustomFieldType;
  help_text: string | null;
  is_required: boolean;
  is_active: boolean;
  position: number;
  default_value: string | null;
  picklist_id: string | null;
  min_value: number | null;
  max_value: number | null;
  min_length: number | null;
  max_length: number | null;
  pattern: string | null;
  /**
   * The live options, inlined by the backend for picklist fields so a form
   * renders from one response rather than one request per select.
   */
  options?: PicklistOption[] | null;
}

/** What one custom field can hold, in every shape the backend stores. */
export type CustomFieldValue = string | number | boolean | string[] | null;

/** A record's tenant-defined values, keyed by `api_name`. */
export type CustomFieldValues = Record<string, CustomFieldValue>;

export interface EntitySchema {
  entity_type: CustomFieldEntityType;
  fields: CustomFieldDefinition[];
}

/* ------------------------------------------------------------------
   Definitions
   ------------------------------------------------------------------ */

export interface CustomFieldInput {
  entity_type: CustomFieldEntityType;
  api_name: string;
  label: string;
  field_type: CustomFieldType;
  help_text?: string | null;
  is_required?: boolean;
  is_active?: boolean;
  position?: number;
  default_value?: string | null;
  picklist_id?: string | null;
  min_value?: number | null;
  max_value?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  pattern?: string | null;
}

/**
 * A patch. `api_name`, `field_type` and `entity_type` are absent because the
 * backend refuses them with a 422 — changing any of them would strand the
 * values already stored, and the supported move is to deactivate the field and
 * add another.
 */
export type CustomFieldPatch = Partial<Omit<CustomFieldInput, 'entity_type' | 'api_name' | 'field_type'>>;

export const listCustomFields = (params?: {
  entity_type?: CustomFieldEntityType;
  include_inactive?: boolean;
}) => api.get<CustomFieldDefinition[]>(`/crm/custom-fields${toQuery(params)}`);

/**
 * The active fields for one record type, with picklist options inlined.
 *
 * What a record form reads. Retired fields are excluded by the backend, so a
 * form drawn from this can never offer one.
 */
export const getEntitySchema = (entityType: CustomFieldEntityType) =>
  api.get<EntitySchema>(`/crm/custom-fields/schema/${entityType}`);

export const createCustomField = (body: CustomFieldInput) =>
  api.post<CustomFieldDefinition>('/crm/custom-fields', body);

export const updateCustomField = (id: string, body: CustomFieldPatch) =>
  api.patch<CustomFieldDefinition>(`/crm/custom-fields/${id}`, body);

/** Retires the field. Values already stored under it are left untouched. */
export const archiveCustomField = (id: string) =>
  api.delete<void>(`/crm/custom-fields/${id}`);

/**
 * Set the display order for one record type.
 *
 * Takes the complete order: the backend refuses a partial list, because "the
 * ids I sent, then everything else somehow" is not an order anybody chose.
 */
export const reorderCustomFields = (entityType: CustomFieldEntityType, order: string[]) =>
  api.post<CustomFieldDefinition[]>('/crm/custom-fields/reorder', {
    entity_type: entityType,
    order,
  });

/* ------------------------------------------------------------------
   Picklists
   ------------------------------------------------------------------ */

export interface PicklistInput {
  name: string;
  api_name: string;
  description?: string | null;
  options?: PicklistOptionInput[];
}

export interface PicklistOptionInput {
  value: string;
  label?: string | null;
  position?: number;
  is_active?: boolean;
  is_default?: boolean;
}

export const listPicklists = (params?: ListParams) =>
  api.get<Page<Picklist>>(`/crm/picklists${toQuery(params)}`);

/** One picklist with every option, active and inactive — the admin view. */
export const getPicklist = (id: string) => api.get<Picklist>(`/crm/picklists/${id}`);

export const createPicklist = (body: PicklistInput) =>
  api.post<Picklist>('/crm/picklists', body);

export const updatePicklist = (id: string, body: Partial<Omit<PicklistInput, 'api_name' | 'options'>>) =>
  api.patch<Picklist>(`/crm/picklists/${id}`, body);

/** Returns 409 while custom fields still draw from the list. */
export const archivePicklist = (id: string) => api.delete<void>(`/crm/picklists/${id}`);

export const addPicklistOption = (picklistId: string, body: PicklistOptionInput) =>
  api.post<PicklistOption>(`/crm/picklists/${picklistId}/options`, body);

export const updatePicklistOption = (
  picklistId: string,
  optionId: string,
  body: Partial<PicklistOptionInput>,
) => api.patch<PicklistOption>(`/crm/picklists/${picklistId}/options/${optionId}`, body);

/** Records already holding the option keep their value. */
export const removePicklistOption = (picklistId: string, optionId: string) =>
  api.delete<void>(`/crm/picklists/${picklistId}/options/${optionId}`);

/* ------------------------------------------------------------------
   Rendering helpers
   ------------------------------------------------------------------ */

/**
 * A stored value as a person should read it.
 *
 * The option `label` is preferred over the stored `value` wherever one is
 * available — that split is the whole reason "EMEA" can be relabelled without
 * touching a record. A value whose option has since been *removed* has no
 * label to find, and falls back to the raw value rather than disappearing:
 * the record still holds it, so the screen must still show it.
 */
export function describeValue(
  definition: CustomFieldDefinition,
  value: CustomFieldValue,
): string {
  if (value === null || value === undefined || value === '') return '—';

  const labelFor = (raw: string): string =>
    definition.options?.find((option) => option.value === raw)?.label ?? raw;

  if (Array.isArray(value)) {
    return value.length ? value.map(labelFor).join(', ') : '—';
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (isPicklistType(definition.field_type)) return labelFor(String(value));
  if (definition.field_type === 'DATE') return formatDate(String(value));
  if (definition.field_type === 'DATETIME') return formatDateTime(String(value));
  return String(value);
}

function formatDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  return Number.isNaN(parsed.valueOf()) ? iso : parsed.toLocaleDateString();
}

function formatDateTime(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.valueOf()) ? iso : parsed.toLocaleString();
}

/**
 * The empty form state for a set of definitions.
 *
 * Defaults are *not* applied here: the backend applies them on create, and
 * pre-filling them in the browser too would mean the value shown depends on
 * which side ran last. The form shows blank, the record comes back with the
 * default, and there is one answer to what a default is.
 */
export function emptyValues(fields: CustomFieldDefinition[]): CustomFieldValues {
  const values: CustomFieldValues = {};
  for (const field of fields) {
    values[field.api_name] = field.field_type === 'MULTI_PICKLIST' ? [] : '';
  }
  return values;
}

/**
 * Drop entries the user never touched, so a patch says only what changed.
 *
 * An empty string *is* a change when the field previously held something —
 * it clears it — so this compares against the record's current document
 * rather than testing for emptiness.
 */
export function changedValues(
  next: CustomFieldValues,
  current: CustomFieldValues | undefined,
): CustomFieldValues {
  const before = current ?? {};
  const changed: CustomFieldValues = {};
  for (const [key, value] of Object.entries(next)) {
    if (JSON.stringify(value ?? '') !== JSON.stringify(before[key] ?? '')) {
      changed[key] = value;
    }
  }
  return changed;
}
