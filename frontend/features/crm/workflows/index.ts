/**
 * Workflow automation (Checkpoint 6) — types and API access.
 *
 * Mirrors `backend/app/products/crm/workflows/schemas.py`. A workflow is
 * `WHEN <trigger> -> IF <conditions> -> THEN <actions>`, evaluated by the
 * backend against a real record change or a periodic scan — nothing here
 * decides whether a rule fires; this module only shapes what an
 * administrator configures and reads back the history of what happened.
 */

import { api } from '@/lib/api-client';
import type { Page, ListParams } from '@/features/shared/types/api';
import { toQuery } from '@/features/shared/types/api';

export type WorkflowEntityType =
  | 'ACCOUNT'
  | 'CONTACT'
  | 'LEAD'
  | 'OPPORTUNITY'
  | 'CAMPAIGN'
  | 'TASK';

export const WORKFLOW_ENTITY_TYPES: WorkflowEntityType[] = [
  'LEAD',
  'OPPORTUNITY',
  'ACCOUNT',
  'CONTACT',
  'CAMPAIGN',
  'TASK',
];

export const ENTITY_TYPE_LABELS: Record<WorkflowEntityType, string> = {
  LEAD: 'Lead',
  OPPORTUNITY: 'Opportunity',
  ACCOUNT: 'Account',
  CONTACT: 'Contact',
  CAMPAIGN: 'Campaign',
  TASK: 'Task',
};

export type WorkflowTriggerType =
  | 'RECORD_CREATED'
  | 'RECORD_UPDATED'
  | 'FIELD_CHANGED'
  | 'STAGE_CHANGED'
  | 'STATUS_CHANGED'
  | 'OWNER_CHANGED'
  | 'SCHEDULED'
  | 'TASK_DUE';

/** Which trigger types apply to which entity — mirrors `WorkflowRuleService._validate_trigger`. */
export function triggersFor(entityType: WorkflowEntityType): WorkflowTriggerType[] {
  if (entityType === 'TASK') return ['RECORD_CREATED', 'RECORD_UPDATED', 'OWNER_CHANGED', 'TASK_DUE'];
  const base: WorkflowTriggerType[] = [
    'RECORD_CREATED',
    'RECORD_UPDATED',
    'FIELD_CHANGED',
    'OWNER_CHANGED',
  ];
  if (entityType === 'OPPORTUNITY') return [...base, 'STAGE_CHANGED', 'SCHEDULED'];
  if (entityType === 'LEAD') return [...base, 'STATUS_CHANGED'];
  return base;
}

export const TRIGGER_LABELS: Record<WorkflowTriggerType, string> = {
  RECORD_CREATED: 'Record is created',
  RECORD_UPDATED: 'Record is updated',
  FIELD_CHANGED: 'A field changes',
  STAGE_CHANGED: 'Stage changes',
  STATUS_CHANGED: 'Status changes',
  OWNER_CHANGED: 'Owner changes',
  SCHEDULED: 'A date field arrives',
  TASK_DUE: 'Due date arrives',
};

/** Date fields a SCHEDULED trigger may watch — mirrors `conditions.SCHEDULED_DATE_FIELDS`. */
export const SCHEDULED_DATE_FIELDS: Partial<Record<WorkflowEntityType, string[]>> = {
  OPPORTUNITY: ['expected_close_date'],
};

export type ConditionOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'greater_than'
  | 'less_than'
  | 'is_empty'
  | 'is_not_empty'
  | 'in'
  | 'not_in';

export const CONDITION_OPERATORS: ConditionOperator[] = [
  'equals',
  'not_equals',
  'contains',
  'not_contains',
  'greater_than',
  'less_than',
  'is_empty',
  'is_not_empty',
  'in',
  'not_in',
];

export const OPERATOR_LABELS: Record<ConditionOperator, string> = {
  equals: 'equals',
  not_equals: 'does not equal',
  contains: 'contains',
  not_contains: 'does not contain',
  greater_than: 'is greater than',
  less_than: 'is less than',
  is_empty: 'is empty',
  is_not_empty: 'is not empty',
  in: 'is one of',
  not_in: 'is not one of',
};

/** An operator that takes no `value` — the condition tests presence, not content. */
export const VALUELESS_OPERATORS: ConditionOperator[] = ['is_empty', 'is_not_empty'];

export interface WorkflowCondition {
  field_key: string;
  operator: ConditionOperator;
  value: unknown;
}

export type WorkflowActionType =
  | 'UPDATE_FIELD'
  | 'ASSIGN_OWNER'
  | 'CREATE_TASK'
  | 'CREATE_ACTIVITY'
  | 'CREATE_NOTE'
  | 'SEND_EMAIL'
  | 'SEND_NOTIFICATION'
  | 'CHANGE_STAGE'
  | 'CHANGE_STATUS';

export const ACTION_LABELS: Record<WorkflowActionType, string> = {
  UPDATE_FIELD: 'Update a field',
  ASSIGN_OWNER: 'Assign owner',
  CREATE_TASK: 'Create a task',
  CREATE_ACTIVITY: 'Log an activity',
  CREATE_NOTE: 'Add a note',
  SEND_EMAIL: 'Send an email',
  SEND_NOTIFICATION: 'Send an in-app notification',
  CHANGE_STAGE: 'Move opportunity stage',
  CHANGE_STATUS: 'Change lead status',
};

/** Which actions apply to which entity — mirrors `WorkflowRuleService._validate_action`. */
export function actionsFor(entityType: WorkflowEntityType): WorkflowActionType[] {
  const common: WorkflowActionType[] = [
    'UPDATE_FIELD',
    'ASSIGN_OWNER',
    'SEND_EMAIL',
    'SEND_NOTIFICATION',
  ];
  const recordLinked: WorkflowActionType[] = ['CREATE_TASK', 'CREATE_ACTIVITY', 'CREATE_NOTE'];
  if (entityType === 'TASK') return common;
  if (entityType === 'OPPORTUNITY') return [...common, ...recordLinked, 'CHANGE_STAGE'];
  if (entityType === 'LEAD') return [...common, ...recordLinked, 'CHANGE_STATUS'];
  return [...common, ...recordLinked];
}

/** Fields `UPDATE_FIELD` may target — mirrors `actions.ALLOWED_UPDATE_FIELDS`. */
export const UPDATABLE_FIELDS: Record<WorkflowEntityType, string[]> = {
  LEAD: [
    'first_name', 'last_name', 'company', 'email', 'phone', 'owner_id', 'priority',
    'expected_deal_size', 'industry', 'website', 'company_size', 'product_interest', 'notes',
  ],
  OPPORTUNITY: [
    'name', 'primary_contact_id', 'owner_id', 'deal_value', 'currency', 'win_probability',
    'expected_close_date', 'health_score', 'forecast_category', 'competitor', 'products', 'notes',
  ],
  ACCOUNT: [
    'name', 'industry', 'website', 'phone', 'company_size', 'annual_revenue', 'status',
    'owner_id', 'health_score', 'source', 'description',
  ],
  CONTACT: [
    'first_name', 'last_name', 'email', 'phone', 'mobile', 'job_title', 'department',
    'owner_id', 'status', 'notes',
  ],
  CAMPAIGN: [
    'name', 'type', 'status', 'owner_id', 'start_date', 'end_date', 'budget',
    'expected_revenue', 'notes',
  ],
  TASK: ['title', 'description', 'priority', 'due_date'],
};

export interface WorkflowAction {
  type: WorkflowActionType;
  [key: string]: unknown;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  entity_type: WorkflowEntityType;
  trigger_type: WorkflowTriggerType;
  trigger_config: Record<string, unknown>;
  condition_logic: 'AND' | 'OR';
  conditions: WorkflowCondition[];
  actions: WorkflowAction[];
  is_active: boolean;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowInput {
  name: string;
  description?: string | null;
  entity_type: WorkflowEntityType;
  trigger_type: WorkflowTriggerType;
  trigger_config?: Record<string, unknown>;
  condition_logic?: 'AND' | 'OR';
  conditions?: WorkflowCondition[];
  actions?: WorkflowAction[];
  position?: number;
}

export interface WorkflowPatch extends Partial<WorkflowInput> {
  is_active?: boolean;
}

export type WorkflowRunStatus = 'SUCCEEDED' | 'PARTIAL' | 'FAILED';

export interface WorkflowActionResult {
  type: string;
  status: 'SUCCEEDED' | 'FAILED';
  detail: string | null;
}

export interface WorkflowRun {
  id: string;
  workflow_rule_id: string;
  entity_type: WorkflowEntityType;
  record_id: string;
  trigger: string;
  correlation_id: string;
  depth: number;
  status: WorkflowRunStatus;
  actions_attempted: number;
  actions_succeeded: number;
  actions_failed: number;
  action_results: WorkflowActionResult[];
  error: string | null;
  retry_count: number;
  started_at: string;
  finished_at: string | null;
  created_at: string;
}

export const listWorkflows = (params?: ListParams) =>
  api.get<Page<Workflow>>(`/crm/workflows${toQuery(params)}`);

export const getWorkflow = (id: string) => api.get<Workflow>(`/crm/workflows/${id}`);

/** Created inactive — activation is a separate, deliberate act. */
export const createWorkflow = (body: WorkflowInput) => api.post<Workflow>('/crm/workflows', body);

export const updateWorkflow = (id: string, body: WorkflowPatch) =>
  api.patch<Workflow>(`/crm/workflows/${id}`, body);

export const archiveWorkflow = (id: string) => api.delete<void>(`/crm/workflows/${id}`);

/** A deactivated copy, named uniquely. */
export const duplicateWorkflow = (id: string) => api.post<Workflow>(`/crm/workflows/${id}/duplicate`);

export const listWorkflowRuns = (id: string, params?: ListParams) =>
  api.get<Page<WorkflowRun>>(`/crm/workflows/${id}/runs${toQuery(params)}`);

/**
 * The ``{{record.<field>}}`` placeholder that names this entity, for form
 * hints — mirrors `emails.variables._FIELDS`'s allow-list per entity.
 * ``ACCOUNT``/``OPPORTUNITY``/``CAMPAIGN`` have a real ``name`` column;
 * ``LEAD``/``CONTACT`` do not and offer the derived ``full_name`` instead.
 * ``TASK`` has no variable vocabulary at all (see `.actions._VARIABLE_ENTITY_TYPES`).
 */
export function recordNamePlaceholder(entityType: WorkflowEntityType): string | null {
  if (entityType === 'TASK') return null;
  if (entityType === 'LEAD' || entityType === 'CONTACT') return '{{record.full_name}}';
  return '{{record.name}}';
}

/** A short, human summary of what a run did, for the history list. */
export function describeRun(run: WorkflowRun): string {
  if (run.actions_attempted === 0) return 'No actions configured';
  if (run.status === 'SUCCEEDED') return `${run.actions_succeeded} action(s) succeeded`;
  if (run.status === 'FAILED') return `${run.actions_failed} action(s) failed`;
  return `${run.actions_succeeded} succeeded, ${run.actions_failed} failed`;
}
