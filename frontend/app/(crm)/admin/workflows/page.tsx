'use client';

import { useCallback, useMemo, useState } from 'react';
import { Loader2, Plus, Trash2, Workflow as WorkflowIcon } from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import { LEAD_STATUSES } from '@/features/crm/leads';
import {
  ACTION_LABELS,
  CONDITION_OPERATORS,
  ENTITY_TYPE_LABELS,
  OPERATOR_LABELS,
  SCHEDULED_DATE_FIELDS,
  TRIGGER_LABELS,
  UPDATABLE_FIELDS,
  VALUELESS_OPERATORS,
  WORKFLOW_ENTITY_TYPES,
  actionsFor,
  archiveWorkflow,
  createWorkflow,
  describeRun,
  duplicateWorkflow,
  getWorkflow,
  listWorkflowRuns,
  listWorkflows,
  recordNamePlaceholder,
  triggersFor,
  updateWorkflow,
  type ConditionOperator,
  type Workflow,
  type WorkflowAction,
  type WorkflowActionType,
  type WorkflowCondition,
  type WorkflowEntityType,
  type WorkflowInput,
  type WorkflowRun,
  type WorkflowTriggerType,
} from '@/features/crm/workflows';

/* ============================================================
   ADMIN — WORKFLOWS

   WHEN a trigger fires on a record -> IF its conditions hold ->
   THEN its actions run. Every action calls the same service a
   person's own click would (update a field, create a task, move
   a stage) — there is no automation-only bypass, so a workflow
   can no more skip a blueprint or a required field than a human
   request could.

   Created inactive, like a blueprint: activation is the moment a
   rule starts acting on real records.
   ============================================================ */

type FormState = WorkflowInput;

function blankForm(): FormState {
  return {
    name: '',
    description: '',
    entity_type: 'LEAD',
    trigger_type: 'RECORD_CREATED',
    trigger_config: {},
    condition_logic: 'AND',
    conditions: [],
    actions: [],
  };
}

function formFromWorkflow(workflow: Workflow): FormState {
  return {
    name: workflow.name,
    description: workflow.description ?? '',
    entity_type: workflow.entity_type,
    trigger_type: workflow.trigger_type,
    trigger_config: { ...workflow.trigger_config },
    condition_logic: workflow.condition_logic,
    conditions: workflow.conditions.map((c) => ({ ...c })),
    actions: workflow.actions.map((a) => ({ ...a })),
  };
}

export default function AdminWorkflowsPage() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayView = can('workflows', 'VIEW');
  const mayCreate = can('workflows', 'CREATE');
  const mayEdit = can('workflows', 'EDIT');
  const mayDelete = can('workflows', 'DELETE');

  const fetcher = useCallback(() => listWorkflows({ page: 1, page_size: 100 }), []);
  const { status, items: workflows, error, reload } = useCollection<Workflow>(fetcher, [mayView], {
    errorMessage: 'Workflows could not be loaded.',
  });

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[] | null>(null);

  const toggleHistory = async (workflow: Workflow) => {
    if (expandedId === workflow.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(workflow.id);
    setRuns(null);
    try {
      const page = await listWorkflowRuns(workflow.id, { page: 1, page_size: 20 });
      setRuns(page.data);
    } catch (caught) {
      notifyError(caught, 'Execution history could not be loaded.');
      setRuns([]);
    }
  };

  const toggleActive = async (workflow: Workflow) => {
    if (!workflow.is_active) {
      const ok = await confirm({
        title: `Activate "${workflow.name}"?`,
        description:
          'From now on it acts on every matching record automatically. Its actions run through the same validated services a person’s own request would — a blueprint or required field it would refuse stays refused.',
        confirmLabel: 'Activate',
      });
      if (!ok) return;
    }
    try {
      await updateWorkflow(workflow.id, { is_active: !workflow.is_active });
      notifySuccess(workflow.is_active ? 'Workflow disabled' : 'Workflow activated', workflow.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The workflow could not be updated.');
    }
  };

  const duplicate = async (workflow: Workflow) => {
    try {
      const copy = await duplicateWorkflow(workflow.id);
      notifySuccess('Workflow duplicated', copy.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The workflow could not be duplicated.');
    }
  };

  const archive = async (workflow: Workflow) => {
    const ok = await confirm({
      title: `Delete "${workflow.name}"?`,
      description: 'It stops running immediately. Records it already acted on are unaffected.',
      confirmLabel: 'Delete workflow',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveWorkflow(workflow.id);
      notifySuccess('Workflow deleted', workflow.name);
      if (expandedId === workflow.id) setExpandedId(null);
      reload();
    } catch (caught) {
      notifyError(caught, 'The workflow could not be deleted.');
    }
  };

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Workflow | null>(null);
  const [form, setForm] = useState<FormState>(blankForm());
  const { pending, error: saveError, clearError, run } = useMutation();

  const openCreate = () => {
    setEditing(null);
    setForm(blankForm());
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = async (workflow: Workflow) => {
    try {
      const detail = await getWorkflow(workflow.id);
      setEditing(detail);
      setForm(formFromWorkflow(detail));
      clearError();
      setDrawerOpen(true);
    } catch (caught) {
      notifyError(caught, 'The workflow could not be opened.');
    }
  };

  const save = async () => {
    if (!form.name.trim()) return;
    const payload: WorkflowInput = {
      ...form,
      name: form.name.trim(),
      description: form.description?.trim() || null,
    };
    const saved = await run(() =>
      editing ? updateWorkflow(editing.id, payload) : createWorkflow(payload),
    );
    if (saved === undefined) return;
    setDrawerOpen(false);
    notifySuccess(editing ? 'Workflow updated' : 'Workflow created', saved.name);
    reload();
  };

  if (!mayView) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="font-display txt text-[22px] font-extrabold">Workflows</h1>
        <p className="txt-muted mt-1 text-[13px]">
          You do not have permission to view this organization&apos;s automation.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-500 to-indigo-600">
            <WorkflowIcon className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Workflows</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              WHEN something happens → IF conditions hold → THEN act on the record.
            </p>
          </div>
        </div>
        {mayCreate && (
          <button
            type="button"
            onClick={openCreate}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <Plus className="h-4 w-4" /> New workflow
          </button>
        )}
      </div>

      {status === 'error' ? (
        <ListError message={error ?? 'Workflows could not be loaded.'} onRetry={reload} />
      ) : status === 'loading' ? (
        <Loader2 className="txt-faint h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
      ) : workflows.length === 0 ? (
        <p className="txt-muted text-[13px]">
          No workflows yet. Records only follow the product&apos;s built-in behaviour until you
          add one.
        </p>
      ) : (
        <ul className="space-y-2" data-testid="workflow-list">
          {workflows.map((workflow) => (
            <li key={workflow.id} className="ctl rounded-lg px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void openEdit(workflow)}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="txt text-[13px] font-semibold">{workflow.name}</p>
                  <p className="txt-faint text-[11px]">
                    {ENTITY_TYPE_LABELS[workflow.entity_type]} · WHEN{' '}
                    {TRIGGER_LABELS[workflow.trigger_type].toLowerCase()} →{' '}
                    {workflow.actions.length} action{workflow.actions.length === 1 ? '' : 's'}
                  </p>
                </button>
                <StatusBadge
                  label={workflow.is_active ? 'Active' : 'Draft'}
                  variant={workflow.is_active ? 'success' : 'neutral'}
                />
                <button
                  type="button"
                  onClick={() => void toggleHistory(workflow)}
                  className="txt-faint text-[12px] underline transition hover:opacity-70"
                >
                  History
                </button>
                {mayEdit && (
                  <button
                    type="button"
                    onClick={() => void toggleActive(workflow)}
                    className="txt-faint text-[12px] underline transition hover:opacity-70"
                  >
                    {workflow.is_active ? 'Disable' : 'Activate'}
                  </button>
                )}
                {mayCreate && (
                  <button
                    type="button"
                    onClick={() => void duplicate(workflow)}
                    className="txt-faint text-[12px] underline transition hover:opacity-70"
                  >
                    Duplicate
                  </button>
                )}
                {mayDelete && (
                  <button
                    type="button"
                    aria-label={`Delete ${workflow.name}`}
                    onClick={() => void archive(workflow)}
                    className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {expandedId === workflow.id && <RunHistory runs={runs} />}
            </li>
          ))}
        </ul>
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit workflow' : 'New workflow'}
        subtitle={editing ? undefined : 'Created as a draft. Configure it, then activate it.'}
        width="max-w-2xl"
        footer={
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={pending}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {editing ? 'Save changes' : 'Create workflow'}
            </button>
          </div>
        }
      >
        <WorkflowForm form={form} setForm={setForm} saveError={saveError} />
      </SlideDrawer>
    </div>
  );
}

/* ------------------------------------------------------------
   The WHEN / IF / THEN form
   ------------------------------------------------------------ */

function WorkflowForm({
  form,
  setForm,
  saveError,
}: {
  form: FormState;
  setForm: (form: FormState) => void;
  saveError: string | null;
}) {
  const entityType = form.entity_type;
  const availableTriggers = useMemo(() => triggersFor(entityType), [entityType]);
  const availableActions = useMemo(() => actionsFor(entityType), [entityType]);

  const setEntityType = (next: WorkflowEntityType) => {
    const nextTriggers = triggersFor(next);
    setForm({
      ...form,
      entity_type: next,
      trigger_type: nextTriggers.includes(form.trigger_type) ? form.trigger_type : nextTriggers[0],
      trigger_config: {},
      actions: [],
    });
  };

  return (
    <div className="space-y-5">
      <FormError message={saveError} />

      <FormField label="Name" required>
        <FormInput
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Follow up on qualified leads"
        />
      </FormField>
      <FormField label="Description">
        <FormTextarea
          rows={2}
          value={form.description ?? ''}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      </FormField>
      <FormField label="Applies to" required>
        <FormSelect
          value={entityType}
          onChange={(e) => setEntityType(e.target.value as WorkflowEntityType)}
          options={WORKFLOW_ENTITY_TYPES.map((v) => ({ value: v, label: ENTITY_TYPE_LABELS[v] }))}
        />
      </FormField>

      <section className="bd space-y-3 rounded-xl border p-4">
        <h3 className="txt text-[12px] font-bold tracking-wide uppercase">When</h3>
        <FormField label="Trigger" required>
          <FormSelect
            value={form.trigger_type}
            onChange={(e) =>
              setForm({
                ...form,
                trigger_type: e.target.value as WorkflowTriggerType,
                trigger_config: {},
              })
            }
            options={availableTriggers.map((v) => ({ value: v, label: TRIGGER_LABELS[v] }))}
          />
        </FormField>
        <TriggerConfigEditor
          entityType={entityType}
          triggerType={form.trigger_type}
          config={form.trigger_config ?? {}}
          onChange={(trigger_config) => setForm({ ...form, trigger_config })}
        />
      </section>

      <section className="bd space-y-3 rounded-xl border p-4">
        <h3 className="txt text-[12px] font-bold tracking-wide uppercase">If (optional)</h3>
        <ConditionsEditor
          logic={form.condition_logic ?? 'AND'}
          conditions={form.conditions ?? []}
          onChange={(condition_logic, conditions) =>
            setForm({ ...form, condition_logic, conditions })
          }
        />
      </section>

      <section className="bd space-y-3 rounded-xl border p-4">
        <h3 className="txt text-[12px] font-bold tracking-wide uppercase">Then</h3>
        <ActionsEditor
          entityType={entityType}
          availableActions={availableActions}
          actions={form.actions ?? []}
          onChange={(actions) => setForm({ ...form, actions })}
        />
      </section>
    </div>
  );
}

function TriggerConfigEditor({
  entityType,
  triggerType,
  config,
  onChange,
}: {
  entityType: WorkflowEntityType;
  triggerType: WorkflowTriggerType;
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const set = (key: string, value: unknown) => onChange({ ...config, [key]: value });

  if (triggerType === 'FIELD_CHANGED') {
    return (
      <div className="grid grid-cols-3 gap-2">
        <FormField label="Field" required hint="A built-in column's API name.">
          <FormInput
            value={String(config.field ?? '')}
            onChange={(e) => set('field', e.target.value)}
            placeholder="priority"
          />
        </FormField>
        <FormField label="Changes to" hint="Leave blank to match any new value.">
          <FormInput
            value={String(config.to ?? '')}
            onChange={(e) => set('to', e.target.value || undefined)}
          />
        </FormField>
        <FormField label="Changes from" hint="Leave blank to match any prior value.">
          <FormInput
            value={String(config.from ?? '')}
            onChange={(e) => set('from', e.target.value || undefined)}
          />
        </FormField>
      </div>
    );
  }

  if (triggerType === 'STAGE_CHANGED') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <FormField label="Moves to stage" hint="Exact pipeline stage name.">
          <FormInput
            value={String(config.to_stage_name ?? '')}
            onChange={(e) => set('to_stage_name', e.target.value || undefined)}
            placeholder="Closed Won"
          />
        </FormField>
        <FormField label="From stage">
          <FormInput
            value={String(config.from_stage_name ?? '')}
            onChange={(e) => set('from_stage_name', e.target.value || undefined)}
          />
        </FormField>
      </div>
    );
  }

  if (triggerType === 'STATUS_CHANGED') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <FormField label="Changes to">
          <FormSelect
            value={String(config.to ?? '')}
            onChange={(e) => set('to', e.target.value || undefined)}
            placeholder="Any status"
            options={LEAD_STATUSES.map((s) => ({ value: s, label: s }))}
          />
        </FormField>
        <FormField label="Changes from">
          <FormSelect
            value={String(config.from ?? '')}
            onChange={(e) => set('from', e.target.value || undefined)}
            placeholder="Any status"
            options={LEAD_STATUSES.map((s) => ({ value: s, label: s }))}
          />
        </FormField>
      </div>
    );
  }

  if (triggerType === 'SCHEDULED') {
    const fields = SCHEDULED_DATE_FIELDS[entityType] ?? [];
    return (
      <div className="grid grid-cols-2 gap-2">
        <FormField label="Date field" required>
          <FormSelect
            value={String(config.date_field ?? '')}
            onChange={(e) => set('date_field', e.target.value)}
            placeholder="Choose…"
            options={fields.map((f) => ({ value: f, label: f }))}
          />
        </FormField>
        <FormField
          label="Offset (minutes)"
          required
          hint="0 fires as it passes; negative fires that many minutes before."
        >
          <FormInput
            type="number"
            value={String(config.offset_minutes ?? 0)}
            onChange={(e) => set('offset_minutes', Number(e.target.value))}
          />
        </FormField>
      </div>
    );
  }

  if (triggerType === 'TASK_DUE') {
    return (
      <FormField
        label="Offset (minutes)"
        required
        hint="0 fires as the due date passes; negative fires that many minutes before."
      >
        <FormInput
          type="number"
          value={String(config.offset_minutes ?? 0)}
          onChange={(e) => set('offset_minutes', Number(e.target.value))}
        />
      </FormField>
    );
  }

  return null;
}

/* ------------------------------------------------------------
   Conditions
   ------------------------------------------------------------ */

function ConditionsEditor({
  logic,
  conditions,
  onChange,
}: {
  logic: 'AND' | 'OR';
  conditions: WorkflowCondition[];
  onChange: (logic: 'AND' | 'OR', conditions: WorkflowCondition[]) => void;
}) {
  const update = (index: number, patch: Partial<WorkflowCondition>) => {
    const next = conditions.map((c, i) => (i === index ? { ...c, ...patch } : c));
    onChange(logic, next);
  };
  const remove = (index: number) => onChange(logic, conditions.filter((_, i) => i !== index));
  const add = () =>
    onChange(logic, [...conditions, { field_key: '', operator: 'equals', value: '' }]);

  return (
    <div className="space-y-2">
      {conditions.length > 1 && (
        <FormField label="Combine with" className="w-[140px]">
          <FormSelect
            value={logic}
            onChange={(e) => onChange(e.target.value as 'AND' | 'OR', conditions)}
            options={[
              { value: 'AND', label: 'AND (all)' },
              { value: 'OR', label: 'OR (any)' },
            ]}
          />
        </FormField>
      )}
      {conditions.length === 0 && (
        <p className="txt-faint text-[12px]">No conditions — the trigger alone is enough.</p>
      )}
      {conditions.map((condition, index) => (
        <div key={index} className="flex flex-wrap items-end gap-2">
          <FormField label="Field" className="w-[160px]">
            <FormInput
              value={condition.field_key}
              onChange={(e) => update(index, { field_key: e.target.value })}
              placeholder="industry"
            />
          </FormField>
          <FormField label="Operator" className="w-[170px]">
            <FormSelect
              value={condition.operator}
              onChange={(e) => update(index, { operator: e.target.value as ConditionOperator })}
              options={CONDITION_OPERATORS.map((op) => ({ value: op, label: OPERATOR_LABELS[op] }))}
            />
          </FormField>
          {!VALUELESS_OPERATORS.includes(condition.operator) && (
            <FormField label="Value" className="w-[170px]">
              <FormInput
                value={String(condition.value ?? '')}
                onChange={(e) => update(index, { value: e.target.value })}
              />
            </FormField>
          )}
          <button
            type="button"
            aria-label="Remove condition"
            onClick={() => remove(index)}
            className="ctl mb-2 rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="ctl bd rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
      >
        <Plus className="mr-1 inline h-3 w-3" /> Add condition
      </button>
    </div>
  );
}

/* ------------------------------------------------------------
   Actions
   ------------------------------------------------------------ */

function ActionsEditor({
  entityType,
  availableActions,
  actions,
  onChange,
}: {
  entityType: WorkflowEntityType;
  availableActions: WorkflowActionType[];
  actions: WorkflowAction[];
  onChange: (actions: WorkflowAction[]) => void;
}) {
  const update = (index: number, action: WorkflowAction) =>
    onChange(actions.map((a, i) => (i === index ? action : a)));
  const remove = (index: number) => onChange(actions.filter((_, i) => i !== index));
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= actions.length) return;
    const next = [...actions];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };
  const add = () => onChange([...actions, { type: availableActions[0] }]);

  return (
    <div className="space-y-3">
      {actions.length === 0 && (
        <p className="txt-faint text-[12px]">
          No actions yet. A workflow with none can be activated but does nothing.
        </p>
      )}
      {actions.map((action, index) => (
        <div key={index} className="bd space-y-2 rounded-lg border p-3">
          <div className="flex items-center gap-2">
            <FormField label="Action" className="flex-1">
              <FormSelect
                value={action.type}
                onChange={(e) =>
                  update(index, { type: e.target.value as WorkflowActionType })
                }
                options={availableActions.map((t) => ({ value: t, label: ACTION_LABELS[t] }))}
              />
            </FormField>
            <div className="flex gap-1 pb-2.5">
              <button
                type="button"
                aria-label="Move up"
                disabled={index === 0}
                onClick={() => move(index, -1)}
                className="ctl rounded-lg px-2 py-1 text-[11px] disabled:opacity-30"
              >
                ↑
              </button>
              <button
                type="button"
                aria-label="Move down"
                disabled={index === actions.length - 1}
                onClick={() => move(index, 1)}
                className="ctl rounded-lg px-2 py-1 text-[11px] disabled:opacity-30"
              >
                ↓
              </button>
              <button
                type="button"
                aria-label="Remove action"
                onClick={() => remove(index)}
                className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <ActionFields
            entityType={entityType}
            action={action}
            onChange={(next) => update(index, next)}
          />
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="ctl bd rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
      >
        <Plus className="mr-1 inline h-3 w-3" /> Add action
      </button>
    </div>
  );
}

function ActionFields({
  entityType,
  action,
  onChange,
}: {
  entityType: WorkflowEntityType;
  action: WorkflowAction;
  onChange: (action: WorkflowAction) => void;
}) {
  const set = (key: string, value: unknown) => onChange({ ...action, [key]: value });

  if (action.type === 'UPDATE_FIELD') {
    const fields = UPDATABLE_FIELDS[entityType] ?? [];
    return (
      <div className="grid grid-cols-2 gap-2">
        <FormField label="Field">
          <FormSelect
            value={String(action.field ?? '')}
            onChange={(e) => set('field', e.target.value)}
            placeholder="Choose…"
            options={fields.map((f) => ({ value: f, label: f }))}
          />
        </FormField>
        <FormField label="New value">
          <FormInput
            value={String(action.value ?? '')}
            onChange={(e) => set('value', e.target.value)}
          />
        </FormField>
      </div>
    );
  }

  if (action.type === 'ASSIGN_OWNER') {
    return (
      <FormField label="Owner's user id" hint="A member of this organization.">
        <FormInput
          value={String(action.owner_id ?? '')}
          onChange={(e) => set('owner_id', e.target.value)}
        />
      </FormField>
    );
  }

  if (action.type === 'CREATE_TASK') {
    const nameVar = recordNamePlaceholder(entityType);
    return (
      <div className="grid grid-cols-2 gap-2">
        <FormField label="Title" hint={nameVar ? `${nameVar} is available.` : undefined}>
          <FormInput
            value={String(action.title ?? '')}
            onChange={(e) => set('title', e.target.value)}
            placeholder={nameVar ? `Follow up with ${nameVar}` : 'Follow up'}
          />
        </FormField>
        <FormField label="Due in (minutes)">
          <FormInput
            type="number"
            value={String(action.due_offset_minutes ?? '')}
            onChange={(e) =>
              set('due_offset_minutes', e.target.value ? Number(e.target.value) : undefined)
            }
          />
        </FormField>
        <FormField label="Priority" className="col-span-2">
          <FormSelect
            value={String(action.priority ?? 'MEDIUM')}
            onChange={(e) => set('priority', e.target.value)}
            options={['LOW', 'MEDIUM', 'HIGH'].map((p) => ({ value: p, label: p }))}
          />
        </FormField>
      </div>
    );
  }

  if (action.type === 'CREATE_ACTIVITY') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <FormField label="Subject">
          <FormInput
            value={String(action.subject ?? '')}
            onChange={(e) => set('subject', e.target.value)}
          />
        </FormField>
        <FormField label="Type">
          <FormSelect
            value={String(action.activity_type ?? 'TASK')}
            onChange={(e) => set('activity_type', e.target.value)}
            options={['CALL', 'EMAIL', 'MEETING', 'NOTE', 'TASK'].map((t) => ({
              value: t,
              label: t,
            }))}
          />
        </FormField>
      </div>
    );
  }

  if (action.type === 'CREATE_NOTE') {
    const nameVar = recordNamePlaceholder(entityType);
    return (
      <FormField label="Note body" hint={nameVar ? `${nameVar} is available.` : undefined}>
        <FormTextarea
          rows={2}
          value={String(action.body ?? '')}
          onChange={(e) => set('body', e.target.value)}
        />
      </FormField>
    );
  }

  if (action.type === 'SEND_EMAIL') {
    const nameVar = recordNamePlaceholder(entityType);
    return (
      <div className="space-y-2">
        <FormField label="Recipient" hint="OWNER sends to the record's owner.">
          <FormSelect
            value={String((action.recipient as { kind?: string } | undefined)?.kind ?? 'OWNER')}
            onChange={(e) => set('recipient', { kind: e.target.value })}
            options={[
              { value: 'OWNER', label: "Record's owner" },
              { value: 'STATIC', label: 'A fixed address' },
            ]}
          />
        </FormField>
        {(action.recipient as { kind?: string } | undefined)?.kind === 'STATIC' && (
          <FormField label="Address">
            <FormInput
              value={String((action.recipient as { address?: string } | undefined)?.address ?? '')}
              onChange={(e) => set('recipient', { kind: 'STATIC', address: e.target.value })}
            />
          </FormField>
        )}
        <FormField label="Subject">
          <FormInput
            value={String(action.subject ?? '')}
            onChange={(e) => set('subject', e.target.value)}
          />
        </FormField>
        <FormField
          label="Body"
          hint={nameVar ? `${nameVar}, {{sender.name}} and similar are available.` : undefined}
        >
          <FormTextarea
            rows={3}
            value={String(action.body_text ?? '')}
            onChange={(e) => set('body_text', e.target.value)}
          />
        </FormField>
      </div>
    );
  }

  if (action.type === 'SEND_NOTIFICATION') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <FormField label="Title">
          <FormInput
            value={String(action.title ?? '')}
            onChange={(e) => set('title', e.target.value)}
          />
        </FormField>
        <FormField label="Body">
          <FormInput
            value={String(action.body ?? '')}
            onChange={(e) => set('body', e.target.value)}
          />
        </FormField>
      </div>
    );
  }

  if (action.type === 'CHANGE_STAGE') {
    return (
      <FormField label="Target stage" hint="Exact pipeline stage name.">
        <FormInput
          value={String(action.stage_name ?? '')}
          onChange={(e) => set('stage_name', e.target.value)}
          placeholder="Closed Won"
        />
      </FormField>
    );
  }

  if (action.type === 'CHANGE_STATUS') {
    return (
      <FormField label="Target status">
        <FormSelect
          value={String(action.status ?? '')}
          onChange={(e) => set('status', e.target.value)}
          placeholder="Choose…"
          options={LEAD_STATUSES.map((s) => ({ value: s, label: s }))}
        />
      </FormField>
    );
  }

  return null;
}

/* ------------------------------------------------------------
   Execution history
   ------------------------------------------------------------ */

function RunHistory({ runs }: { runs: WorkflowRun[] | null }) {
  return (
    <div className="bd mt-3 space-y-2 border-t pt-3">
      {runs === null ? (
        <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Loading" />
      ) : runs.length === 0 ? (
        <p className="txt-faint text-[12px]">No executions yet.</p>
      ) : (
        runs.map((run) => (
          <div key={run.id} className="flex flex-wrap items-center gap-2 text-[12px]">
            <StatusBadge
              label={run.status}
              variant={
                run.status === 'SUCCEEDED'
                  ? 'success'
                  : run.status === 'PARTIAL'
                    ? 'warning'
                    : 'danger'
              }
            />
            <span className="txt-faint">{run.trigger}</span>
            <span className="txt-muted">{describeRun(run)}</span>
            <span className="txt-faint ml-auto">
              {new Date(run.created_at).toLocaleString()}
            </span>
          </div>
        ))
      )}
    </div>
  );
}
