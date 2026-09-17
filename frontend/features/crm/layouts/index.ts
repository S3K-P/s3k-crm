/**
 * Record layouts (the admin form/layout builder, Checkpoint 4) — types and
 * API access.
 *
 * Mirrors `backend/app/products/crm/layouts/schemas.py`. A layout arranges an
 * entity type's built-in and tenant-defined fields into sections, and may
 * attach conditional rules to a placed custom field — see `evaluate.ts` for
 * how a rule is decided (a mirror of the backend's own evaluator, never the
 * authority on its own).
 */

import { api } from '@/lib/api-client';
import type { CustomFieldEntityType } from '@/features/crm/custom-fields';
import type { LayoutFieldRule as EvaluatorRule } from './evaluate';

/** Entity types the layout builder covers — narrower than custom fields. */
export type LayoutEntityType = 'ACCOUNT' | 'CONTACT' | 'LEAD' | 'OPPORTUNITY';

export const LAYOUT_ENTITY_TYPES: LayoutEntityType[] = [
  'ACCOUNT',
  'CONTACT',
  'LEAD',
  'OPPORTUNITY',
];

export type LayoutStatus = 'DRAFT' | 'PUBLISHED';

/**
 * Which screen a layout arranges fields for (Checkpoint 9 — Zoho field/layout
 * parity). Mirrors `backend/app/products/crm/layouts/models.py::LayoutType`.
 */
export type LayoutType = 'CREATE' | 'QUICK_CREATE' | 'DETAIL';

export const LAYOUT_TYPES: LayoutType[] = ['CREATE', 'QUICK_CREATE', 'DETAIL'];

export const LAYOUT_TYPE_LABELS: Record<LayoutType, string> = {
  CREATE: 'Create',
  QUICK_CREATE: 'Quick Create',
  DETAIL: 'Detail View',
};

export const CUSTOM_FIELD_KEY_PREFIX = 'custom:';

export function customFieldKey(apiName: string): string {
  return `${CUSTOM_FIELD_KEY_PREFIX}${apiName}`;
}

export function isCustomFieldKey(fieldKey: string): boolean {
  return fieldKey.startsWith(CUSTOM_FIELD_KEY_PREFIX);
}

export function customFieldApiName(fieldKey: string): string {
  return fieldKey.slice(CUSTOM_FIELD_KEY_PREFIX.length);
}

export interface RecordLayout {
  id: string;
  organization_id: string;
  entity_type: LayoutEntityType;
  layout_type: LayoutType;
  name: string;
  description: string | null;
  status: LayoutStatus;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LayoutField {
  id: string;
  layout_id: string;
  section_id: string;
  field_key: string;
  position: number;
  column_span: number;
  is_visible: boolean;
  is_required_override: boolean | null;
  is_read_only: boolean;
  label_override: string | null;
  help_text_override: string | null;
  placeholder_override: string | null;
}

export interface LayoutSection {
  id: string;
  layout_id: string;
  name: string;
  position: number;
  columns: number;
  fields: LayoutField[];
}

export type LayoutFieldRule = EvaluatorRule & { id: string; layout_id: string; name: string | null };

export interface RecordLayoutDetail extends RecordLayout {
  sections: LayoutSection[];
  rules: LayoutFieldRule[];
}

export interface AvailableFieldInfo {
  field_key: string;
  label: string;
  is_custom: boolean;
  is_required_base: boolean;
  placed: boolean;
}

export interface FieldStateResponse {
  visible: boolean;
  required: boolean | null;
}

/* ------------------------------------------------------------------
   Layouts
   ------------------------------------------------------------------ */

export const listLayouts = (entityType: LayoutEntityType, layoutType?: LayoutType) =>
  api.get<RecordLayout[]>(
    `/crm/layouts?entity_type=${entityType}${layoutType ? `&layout_type=${layoutType}` : ''}`,
  );

/**
 * The live layout a form for `entityType`/`layoutType` should render, or
 * `null` when nothing has been published yet — a fully supported state. A
 * request for `'CREATE'` or `'QUICK_CREATE'` falls back to the published
 * `'DETAIL'` layout (server-side) when neither has one of its own — see
 * `backend/app/products/crm/layouts/repository.py::published_for_with_fallback`.
 */
export const getPublishedLayout = (entityType: LayoutEntityType, layoutType: LayoutType = 'DETAIL') =>
  api.get<RecordLayoutDetail | null>(
    `/crm/layouts/published?entity_type=${entityType}&layout_type=${layoutType}`,
  );

export const getLayout = (id: string) => api.get<RecordLayoutDetail>(`/crm/layouts/${id}`);

export const listAvailableFields = (layoutId: string) =>
  api.get<AvailableFieldInfo[]>(`/crm/layouts/${layoutId}/available-fields`);

export const createLayout = (body: {
  entity_type: LayoutEntityType;
  layout_type?: LayoutType;
  name: string;
  description?: string | null;
}) => api.post<RecordLayout>('/crm/layouts', body);

export const updateLayout = (id: string, body: { name?: string; description?: string | null }) =>
  api.patch<RecordLayout>(`/crm/layouts/${id}`, body);

export const archiveLayout = (id: string) => api.delete<void>(`/crm/layouts/${id}`);

export const publishLayout = (id: string) =>
  api.post<RecordLayoutDetail>(`/crm/layouts/${id}/publish`);

export const unpublishLayout = (id: string) => api.post<RecordLayout>(`/crm/layouts/${id}/unpublish`);

export const evaluateLayout = (id: string, values: Record<string, unknown>) =>
  api.post<{ states: Record<string, FieldStateResponse> }>(`/crm/layouts/${id}/evaluate`, {
    values,
  });

/* ------------------------------------------------------------------
   Sections
   ------------------------------------------------------------------ */

export const addSection = (layoutId: string, body: { name: string; position?: number; columns?: number }) =>
  api.post<LayoutSection>(`/crm/layouts/${layoutId}/sections`, body);

export const updateSection = (
  layoutId: string,
  sectionId: string,
  body: { name?: string; position?: number; columns?: number },
) => api.patch<LayoutSection>(`/crm/layouts/${layoutId}/sections/${sectionId}`, body);

export const removeSection = (layoutId: string, sectionId: string) =>
  api.delete<void>(`/crm/layouts/${layoutId}/sections/${sectionId}`);

/* ------------------------------------------------------------------
   Fields
   ------------------------------------------------------------------ */

export interface LayoutFieldInput {
  section_id: string;
  field_key: string;
  position?: number;
  column_span?: number;
  is_visible?: boolean;
  is_required_override?: boolean | null;
  is_read_only?: boolean;
  label_override?: string | null;
  help_text_override?: string | null;
  placeholder_override?: string | null;
}

export const addField = (layoutId: string, body: LayoutFieldInput) =>
  api.post<LayoutField>(`/crm/layouts/${layoutId}/fields`, body);

export const updateField = (
  layoutId: string,
  fieldId: string,
  body: Partial<LayoutFieldInput> & { clear_required_override?: boolean },
) => api.patch<LayoutField>(`/crm/layouts/${layoutId}/fields/${fieldId}`, body);

export const removeField = (layoutId: string, fieldId: string) =>
  api.delete<void>(`/crm/layouts/${layoutId}/fields/${fieldId}`);

export const reorderFields = (
  layoutId: string,
  fields: { field_id: string; section_id: string; position: number }[],
) => api.post<LayoutField[]>(`/crm/layouts/${layoutId}/fields/reorder`, { fields });

/* ------------------------------------------------------------------
   Rules
   ------------------------------------------------------------------ */

export interface LayoutFieldRuleInput {
  name?: string | null;
  target_field_key: string;
  logic?: 'AND' | 'OR';
  conditions: { field_key: string; operator: string; value: unknown }[];
  effect_visible?: boolean;
  effect_required?: boolean | null;
}

export const addRule = (layoutId: string, body: LayoutFieldRuleInput) =>
  api.post<LayoutFieldRule>(`/crm/layouts/${layoutId}/rules`, body);

export const updateRule = (
  layoutId: string,
  ruleId: string,
  body: Partial<LayoutFieldRuleInput> & { clear_effect_required?: boolean },
) => api.patch<LayoutFieldRule>(`/crm/layouts/${layoutId}/rules/${ruleId}`, body);

export const removeRule = (layoutId: string, ruleId: string) =>
  api.delete<void>(`/crm/layouts/${layoutId}/rules/${ruleId}`);

/** Map a custom-fields entity type onto the narrower set layouts cover. */
export function asLayoutEntityType(entityType: CustomFieldEntityType): LayoutEntityType | null {
  return (LAYOUT_ENTITY_TYPES as string[]).includes(entityType)
    ? (entityType as LayoutEntityType)
    : null;
}
