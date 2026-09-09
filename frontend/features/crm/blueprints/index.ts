/**
 * Blueprints — types and API access.
 *
 * Mirrors `backend/app/products/crm/blueprints/schemas.py`.
 *
 * A blueprint is a tenant's own process laid over a state field a record
 * already has. **It narrows what the product allows and never widens it**: the
 * built-in state machine runs first, and a blueprint can only remove moves from
 * what that permits. So the API refuses a rule for a move the product would not
 * allow anyway, and the configuration screen never has to pretend otherwise.
 *
 * There is no "apply a blueprint" call. It is applied inside the lead and
 * opportunity state-change endpoints, which is where those rules already live;
 * a second way to move a record would be a second place to keep them in step.
 */

import { api } from '@/lib/api-client';
import type { CustomFieldEntityType } from '@/features/crm/custom-fields';

/** Which state column a blueprint governs. */
export type BlueprintField = 'LEAD_STATUS' | 'OPPORTUNITY_STAGE';

export const BLUEPRINT_FIELDS: BlueprintField[] = ['LEAD_STATUS', 'OPPORTUNITY_STAGE'];

export const FIELD_LABELS: Record<BlueprintField, string> = {
  LEAD_STATUS: 'Lead status',
  OPPORTUNITY_STAGE: 'Opportunity stage',
};

/** `from_state` value meaning "from anywhere". */
export const ANY_STATE = '*';

export interface BlueprintTransition {
  id: string;
  blueprint_id: string;
  name: string;
  from_state: string;
  to_state: string;
  /** Columns — built-in or custom — that must hold a value before the move. */
  required_fields: string[];
  /** A `module.ACTION` demanded *in addition to* the endpoint's own. */
  required_permission: string | null;
  require_note: boolean;
  position: number;
}

export interface Blueprint {
  id: string;
  name: string;
  description: string | null;
  field: BlueprintField;
  entity_type: CustomFieldEntityType;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  transition_count: number;
  /** Present on the detail endpoint, absent from list rows. */
  transitions?: BlueprintTransition[] | null;
}

/** A state the governed field can hold, read live from the source of truth. */
export interface BlueprintState {
  value: string;
  label: string;
}

export interface BlueprintStates {
  field: BlueprintField;
  states: BlueprintState[];
}

export interface BlueprintInput {
  name: string;
  field: BlueprintField;
  description?: string | null;
}

/**
 * A patch. `field` is accepted by the API and then refused with a message —
 * its moves name states of that field — so it is offered here for the sake of
 * that message rather than being silently dropped.
 */
export interface BlueprintPatch {
  name?: string;
  description?: string | null;
  is_active?: boolean;
}

export interface TransitionInput {
  to_state: string;
  from_state?: string;
  name?: string | null;
  required_fields?: string[];
  required_permission?: string | null;
  require_note?: boolean;
  position?: number;
}

export const listBlueprints = () => api.get<Blueprint[]>('/crm/blueprints');

/** One blueprint with every move it describes. */
export const getBlueprint = (id: string) => api.get<Blueprint>(`/crm/blueprints/${id}`);

/**
 * The states a field can hold.
 *
 * Fetched per screen rather than compiled in: an opportunity's states are the
 * tenant's own pipeline stages, and offering one that was retired last week is
 * how unsatisfiable processes get built.
 */
export const listBlueprintStates = (field: BlueprintField) =>
  api.get<BlueprintStates>(`/crm/blueprints/states?field=${field}`);

/** Created inactive — activation is a separate, deliberate act. */
export const createBlueprint = (body: BlueprintInput) =>
  api.post<Blueprint>('/crm/blueprints', body);

/**
 * Rename, describe, activate or deactivate.
 *
 * Activating validates the whole process server-side: every move must name a
 * state that still exists, there must be at least one move, and no other
 * blueprint may already govern the field.
 */
export const updateBlueprint = (id: string, body: BlueprintPatch) =>
  api.patch<Blueprint>(`/crm/blueprints/${id}`, body);

/** Retires it. It stops constraining records immediately. */
export const archiveBlueprint = (id: string) => api.delete<void>(`/crm/blueprints/${id}`);

export const addTransition = (blueprintId: string, body: TransitionInput) =>
  api.post<BlueprintTransition>(`/crm/blueprints/${blueprintId}/transitions`, body);

export const updateTransition = (
  blueprintId: string,
  transitionId: string,
  body: Partial<TransitionInput>,
) =>
  api.patch<BlueprintTransition>(
    `/crm/blueprints/${blueprintId}/transitions/${transitionId}`,
    body,
  );

/**
 * Removes a move.
 *
 * Removing the last rule for a destination stops the blueprint constraining
 * that state at all, which is the intended way to relax a process.
 */
export const removeTransition = (blueprintId: string, transitionId: string) =>
  api.delete<void>(`/crm/blueprints/${blueprintId}/transitions/${transitionId}`);

/** A state value as a person reads it, falling back to the raw value. */
export function stateLabel(states: BlueprintState[], value: string): string {
  if (value === ANY_STATE) return 'Any state';
  return states.find((state) => state.value === value)?.label ?? value;
}

/** A one-line summary of what a move demands, for the rule list. */
export function describeRequirements(transition: BlueprintTransition): string {
  const parts: string[] = [];
  if (transition.required_fields.length) {
    parts.push(`needs ${transition.required_fields.join(', ')}`);
  }
  if (transition.require_note) parts.push('needs a note');
  if (transition.required_permission) parts.push(`needs ${transition.required_permission}`);
  return parts.length ? parts.join(' · ') : 'no extra requirements';
}
