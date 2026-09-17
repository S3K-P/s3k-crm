'use client';

import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import { FormError } from '@/components/crm/shared/ListStates';
import { useMutation } from '@/features/shared/hooks/useCollection';
import {
  addRule,
  isCustomFieldKey,
  removeRule,
  updateField,
  updateRule,
  type AvailableFieldInfo,
  type LayoutField,
  type LayoutFieldRule,
  type LayoutFieldRuleInput,
} from '@/features/crm/layouts';

/* ============================================================
   FIELD CONFIG DRAWER

   The settings for one placed field, and — for a custom field —
   the conditional rules that target it. Field settings save
   explicitly ("Save field"), which is this builder's one
   deliberate "unsaved changes" surface: everything else on the
   canvas (drag, add, remove) persists the moment it happens, but
   a still-being-typed label override should not overwrite the
   layout on every keystroke, and the drawer warns before closing
   with edits unsaved.
   ============================================================ */

const OPERATORS: { value: string; label: string }[] = [
  { value: 'equals', label: 'Equals' },
  { value: 'not_equals', label: 'Does not equal' },
  { value: 'contains', label: 'Contains' },
  { value: 'not_contains', label: 'Does not contain' },
  { value: 'greater_than', label: 'Greater than' },
  { value: 'less_than', label: 'Less than' },
  { value: 'is_empty', label: 'Is empty' },
  { value: 'is_not_empty', label: 'Is not empty' },
  { value: 'in', label: 'Is one of (comma-separated)' },
  { value: 'not_in', label: 'Is not one of (comma-separated)' },
];

const NEEDS_VALUE = new Set(['equals', 'not_equals', 'contains', 'not_contains', 'greater_than', 'less_than']);
const NEEDS_LIST = new Set(['in', 'not_in']);

interface FieldConfigDrawerProps {
  layoutId: string;
  field: LayoutField;
  rules: LayoutFieldRule[];
  availableFields: AvailableFieldInfo[];
  onClose: () => void;
  onSaved: () => void;
  mayEdit: boolean;
}

export default function FieldConfigDrawer({
  layoutId,
  field,
  rules,
  availableFields,
  onClose,
  onSaved,
  mayEdit,
}: FieldConfigDrawerProps) {
  const confirm = useConfirm();
  const { pending, error, clearError, run } = useMutation();
  const [dirty, setDirty] = useState(false);
  const [label, setLabel] = useState(field.label_override ?? '');
  const [help, setHelp] = useState(field.help_text_override ?? '');
  const [placeholder, setPlaceholder] = useState(field.placeholder_override ?? '');
  const [columnSpan, setColumnSpan] = useState(field.column_span);
  const [visible, setVisible] = useState(field.is_visible);
  const [readOnly, setReadOnly] = useState(field.is_read_only);
  const [requiredMode, setRequiredMode] = useState<'default' | 'required' | 'optional'>(
    field.is_required_override === null ? 'default' : field.is_required_override ? 'required' : 'optional',
  );

  const isCustom = isCustomFieldKey(field.field_key);

  async function handleClose() {
    if (dirty) {
      const result = await confirm({
        title: 'Discard unsaved field changes?',
        description: 'This field configuration has not been saved.',
        tone: 'warning',
        confirmLabel: 'Discard',
      });
      if (!result) return;
    }
    onClose();
  }

  async function handleSave() {
    clearError();
    const saved = await run(() =>
      updateField(layoutId, field.id, {
        label_override: label.trim() || null,
        help_text_override: help.trim() || null,
        placeholder_override: placeholder.trim() || null,
        column_span: columnSpan,
        is_visible: visible,
        is_read_only: readOnly,
        is_required_override: requiredMode === 'default' ? undefined : requiredMode === 'required',
        clear_required_override: requiredMode === 'default',
      }),
    );
    if (saved) {
      setDirty(false);
      notifySuccess('Field configuration saved.');
      onSaved();
    }
  }

  return (
    <SlideDrawer
      open
      onClose={handleClose}
      title={field.label_override ?? field.field_key}
      subtitle={field.field_key}
      footer={
        mayEdit ? (
          <div className="flex justify-end gap-2">
            <button type="button" onClick={handleClose} className="btn-ghost px-4 py-2 text-[13px]">
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={pending}
              className="btn-primary px-4 py-2 text-[13px] disabled:opacity-60"
            >
              {pending ? 'Saving…' : 'Save field'}
            </button>
          </div>
        ) : undefined
      }
    >
      <div className="space-y-4">
        <FormError message={error} />

        <FormField label="Label">
          <FormInput
            value={label}
            disabled={!mayEdit}
            placeholder={field.field_key}
            onChange={(e) => {
              setLabel(e.target.value);
              setDirty(true);
            }}
          />
        </FormField>

        <FormField label="Help text">
          <FormTextarea
            value={help}
            disabled={!mayEdit}
            onChange={(e) => {
              setHelp(e.target.value);
              setDirty(true);
            }}
          />
        </FormField>

        <FormField label="Placeholder">
          <FormInput
            value={placeholder}
            disabled={!mayEdit}
            onChange={(e) => {
              setPlaceholder(e.target.value);
              setDirty(true);
            }}
          />
        </FormField>

        <FormField label="Width">
          <FormSelect
            options={[
              { value: '1', label: 'Half width' },
              { value: '2', label: 'Full width' },
            ]}
            value={String(columnSpan)}
            disabled={!mayEdit}
            onChange={(e) => {
              setColumnSpan(Number(e.target.value));
              setDirty(true);
            }}
          />
        </FormField>

        <FormField
          label="Required"
          hint={
            isCustom
              ? 'A conditional rule below can still override this while it matches.'
              : 'Built-in fields enforce their own requiredness server-side; this only affects how the field is marked here.'
          }
        >
          <FormSelect
            options={[
              { value: 'default', label: 'Use the field’s default' },
              { value: 'required', label: 'Always required' },
              { value: 'optional', label: 'Always optional' },
            ]}
            value={requiredMode}
            disabled={!mayEdit}
            onChange={(e) => {
              setRequiredMode(e.target.value as typeof requiredMode);
              setDirty(true);
            }}
          />
        </FormField>

        <label className="flex items-center gap-2 text-[13px]">
          <input
            type="checkbox"
            checked={visible}
            disabled={!mayEdit}
            onChange={(e) => {
              setVisible(e.target.checked);
              setDirty(true);
            }}
            className="h-4 w-4"
          />
          <span className="txt font-medium">Visible by default</span>
        </label>

        <label className="flex items-center gap-2 text-[13px]">
          <input
            type="checkbox"
            checked={readOnly}
            disabled={!mayEdit}
            onChange={(e) => {
              setReadOnly(e.target.checked);
              setDirty(true);
            }}
            className="h-4 w-4"
          />
          <span className="txt font-medium">Read-only</span>
        </label>

        {isCustom && (
          <RulesEditor
            layoutId={layoutId}
            field={field}
            rules={rules}
            availableFields={availableFields}
            mayEdit={mayEdit}
            onChanged={onSaved}
          />
        )}
      </div>
    </SlideDrawer>
  );
}

function RulesEditor({
  layoutId,
  field,
  rules,
  availableFields,
  mayEdit,
  onChanged,
}: {
  layoutId: string;
  field: LayoutField;
  rules: LayoutFieldRule[];
  availableFields: AvailableFieldInfo[];
  mayEdit: boolean;
  onChanged: () => void;
}) {
  const confirm = useConfirm();
  const [adding, setAdding] = useState(false);

  async function handleDelete(rule: LayoutFieldRule) {
    const result = await confirm({
      title: 'Remove this rule?',
      tone: 'danger',
      confirmLabel: 'Remove',
    });
    if (!result) return;
    try {
      await removeRule(layoutId, rule.id);
      notifySuccess('Rule removed.');
      onChanged();
    } catch (caught) {
      notifyError(caught, 'Could not remove the rule.');
    }
  }

  return (
    <div className="border-t border-[var(--border)] pt-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="txt text-[13px] font-semibold">Conditional rules</h3>
        {mayEdit && !adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="txt-accent flex items-center gap-1 text-[12px] font-medium"
          >
            <Plus className="h-3.5 w-3.5" /> Add rule
          </button>
        )}
      </div>
      <p className="txt-faint mb-3 text-[11.5px]">
        Show, hide or require this field based on other fields&apos; values. Evaluated on the
        server too, on every save — the form only mirrors it for a live preview.
      </p>

      <div className="space-y-2">
        {rules.map((rule) => (
          <RuleRow
            key={rule.id}
            layoutId={layoutId}
            rule={rule}
            availableFields={availableFields}
            mayEdit={mayEdit}
            onDelete={() => handleDelete(rule)}
            onChanged={onChanged}
          />
        ))}
        {rules.length === 0 && !adding && (
          <p className="txt-faint text-[12px]">No rules yet — this field always uses its default state.</p>
        )}
      </div>

      {adding && (
        <RuleForm
          layoutId={layoutId}
          targetFieldKey={field.field_key}
          availableFields={availableFields}
          onCancel={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function RuleRow({
  layoutId,
  rule,
  availableFields,
  mayEdit,
  onDelete,
  onChanged,
}: {
  layoutId: string;
  rule: LayoutFieldRule;
  availableFields: AvailableFieldInfo[];
  mayEdit: boolean;
  onDelete: () => void;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const label = (key: string) => availableFields.find((f) => f.field_key === key)?.label ?? key;

  if (editing) {
    return (
      <RuleForm
        layoutId={layoutId}
        targetFieldKey={rule.target_field_key}
        availableFields={availableFields}
        initial={rule}
        onCancel={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          onChanged();
        }}
      />
    );
  }

  return (
    <div className="bd surface rounded-lg border p-2.5 text-[12px]">
      <p className="txt">
        If{' '}
        {rule.conditions
          .map((c) => `${label(c.field_key)} ${c.operator.replace(/_/g, ' ')} ${describeValue(c.value)}`)
          .join(rule.logic === 'AND' ? ' and ' : ' or ')}
      </p>
      <p className="txt-muted mt-1">
        Then {rule.effect_visible ? 'show' : 'hide'} this field
        {rule.effect_required === true && ', and require it'}
        {rule.effect_required === false && ', and mark it optional'}.
      </p>
      {mayEdit && (
        <div className="mt-2 flex gap-3">
          <button type="button" onClick={() => setEditing(true)} className="txt-accent text-[11.5px]">
            Edit
          </button>
          <button type="button" onClick={onDelete} className="text-[11.5px] text-red-500">
            Remove
          </button>
        </div>
      )}
    </div>
  );
}

function describeValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined || value === '') return '';
  return String(value);
}

function RuleForm({
  layoutId,
  targetFieldKey,
  availableFields,
  initial,
  onCancel,
  onSaved,
}: {
  layoutId: string;
  targetFieldKey: string;
  availableFields: AvailableFieldInfo[];
  initial?: LayoutFieldRule;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { pending, error, clearError, run } = useMutation();
  const [logic, setLogic] = useState<'AND' | 'OR'>(initial?.logic ?? 'AND');
  const [conditions, setConditions] = useState(
    initial?.conditions.length
      ? initial.conditions.map((c) => ({ ...c, value: describeValue(c.value) }))
      : [{ field_key: '', operator: 'equals', value: '' }],
  );
  const [effectVisible, setEffectVisible] = useState(initial?.effect_visible ?? true);
  const [requiredMode, setRequiredMode] = useState<'unset' | 'required' | 'optional'>(
    initial?.effect_required === undefined || initial?.effect_required === null
      ? 'unset'
      : initial.effect_required
        ? 'required'
        : 'optional',
  );

  function updateCondition(index: number, patch: Partial<(typeof conditions)[number]>) {
    setConditions((prev) => prev.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  async function handleSubmit() {
    clearError();
    const payload: LayoutFieldRuleInput = {
      target_field_key: targetFieldKey,
      logic,
      conditions: conditions
        .filter((c) => c.field_key)
        .map((c) => ({
          field_key: c.field_key,
          operator: c.operator,
          value: NEEDS_LIST.has(c.operator)
            ? String(c.value)
                .split(',')
                .map((v) => v.trim())
                .filter(Boolean)
            : NEEDS_VALUE.has(c.operator)
              ? c.value
              : null,
        })),
      effect_visible: effectVisible,
      effect_required: requiredMode === 'unset' ? null : requiredMode === 'required',
    };
    if (payload.conditions.length === 0) return;

    const id = initial ? initial.id : null;
    const saved = await run(() =>
      id
        ? updateRule(layoutId, id, { ...payload, clear_effect_required: requiredMode === 'unset' })
        : addRule(layoutId, payload),
    );
    if (saved) onSaved();
  }

  return (
    <div className="bd surface mt-2 space-y-3 rounded-lg border p-3">
      <FormError message={error} />
      <div className="flex items-center justify-between">
        <span className="txt text-[11.5px] font-semibold">Conditions</span>
        <FormSelect
          options={[
            { value: 'AND', label: 'Match all (AND)' },
            { value: 'OR', label: 'Match any (OR)' },
          ]}
          value={logic}
          onChange={(e) => setLogic(e.target.value as 'AND' | 'OR')}
          className="w-auto py-1 text-[11.5px]"
        />
      </div>

      {conditions.map((condition, index) => (
        <div key={index} className="flex flex-wrap items-center gap-1.5">
          <FormSelect
            options={availableFields
              .filter((f) => f.field_key !== targetFieldKey)
              .map((f) => ({ value: f.field_key, label: f.label }))}
            placeholder="Field…"
            value={condition.field_key}
            onChange={(e) => updateCondition(index, { field_key: e.target.value })}
            className="w-[38%] py-1 text-[11.5px]"
          />
          <FormSelect
            options={OPERATORS}
            value={condition.operator}
            onChange={(e) => updateCondition(index, { operator: e.target.value })}
            className="w-[34%] py-1 text-[11.5px]"
          />
          {(NEEDS_VALUE.has(condition.operator) || NEEDS_LIST.has(condition.operator)) && (
            <FormInput
              value={String(condition.value ?? '')}
              onChange={(e) => updateCondition(index, { value: e.target.value })}
              placeholder="Value"
              className="w-[24%] py-1 text-[11.5px]"
            />
          )}
          <button
            type="button"
            onClick={() => setConditions((prev) => prev.filter((_, i) => i !== index))}
            className="rounded p-1 text-red-500/70 hover:bg-red-500/10"
            aria-label="Remove condition"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => setConditions((prev) => [...prev, { field_key: '', operator: 'equals', value: '' }])}
        className="txt-accent text-[11.5px] font-medium"
      >
        + Add condition
      </button>

      <div className="border-t border-[var(--border)] pt-2">
        <span className="txt text-[11.5px] font-semibold">Then</span>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <FormSelect
            options={[
              { value: 'true', label: 'Show the field' },
              { value: 'false', label: 'Hide the field' },
            ]}
            value={String(effectVisible)}
            onChange={(e) => setEffectVisible(e.target.value === 'true')}
            className="w-auto py-1 text-[11.5px]"
          />
          <FormSelect
            options={[
              { value: 'unset', label: 'No change to required' },
              { value: 'required', label: 'Require it' },
              { value: 'optional', label: 'Mark it optional' },
            ]}
            value={requiredMode}
            onChange={(e) => setRequiredMode(e.target.value as typeof requiredMode)}
            className="w-auto py-1 text-[11.5px]"
          />
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="btn-ghost px-3 py-1.5 text-[12px]">
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={pending || conditions.every((c) => !c.field_key)}
          className="btn-primary px-3 py-1.5 text-[12px] disabled:opacity-60"
        >
          {pending ? 'Saving…' : 'Save rule'}
        </button>
      </div>
    </div>
  );
}
