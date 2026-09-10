'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  ListChecks,
  Loader2,
  Pencil,
  Plus,
  SlidersHorizontal,
  Trash2,
} from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import Tabs from '@/components/crm/shared/Tabs';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import {
  addPicklistOption,
  archiveCustomField,
  archivePicklist,
  createCustomField,
  createPicklist,
  getPicklist,
  isPicklistType,
  listCustomFields,
  listPicklists,
  removePicklistOption,
  reorderCustomFields,
  updateCustomField,
  updatePicklistOption,
  CUSTOM_FIELD_ENTITY_TYPES,
  CUSTOM_FIELD_TYPES,
  type CustomFieldDefinition,
  type CustomFieldEntityType,
  type CustomFieldInput,
  type CustomFieldType,
  type Picklist,
  type PicklistOption,
} from '@/features/crm/custom-fields';

/* ============================================================
   ADMIN — CUSTOM FIELDS & PICKLISTS

   The screen an administrator configures the tenant's own data
   model from. Everything here is a real API round trip; nothing
   is stored in the browser.

   Two things the UI deliberately does *not* offer, because the
   backend refuses them and a control that always fails is worse
   than no control:

   - renaming a field's API name, or changing its type — both
     would strand the values already stored, and the supported
     move is to deactivate and add another;
   - deleting a picklist a field still draws from — the refusal
     names the fields, and that message is surfaced as-is.

   Retiring is kept distinct from deleting throughout, because
   the two mean different things here: a deactivated field or
   option stops being *offered* while every record already
   holding a value keeps it. The confirmations say so rather
   than leaving an administrator to discover it.
   ============================================================ */

const ENTITY_OPTIONS = CUSTOM_FIELD_ENTITY_TYPES.map((value) => ({
  value,
  label: titleCase(value),
}));

const TYPE_OPTIONS = CUSTOM_FIELD_TYPES.map((value) => ({
  value,
  label: titleCase(value),
}));

const EMPTY_FIELD: CustomFieldInput = {
  entity_type: 'LEAD',
  api_name: '',
  label: '',
  field_type: 'TEXT',
  help_text: '',
  is_required: false,
  is_active: true,
  default_value: '',
  picklist_id: null,
};

export default function AdminCustomFieldsPage() {
  const { can } = usePermissions();

  if (!can('custom_fields', 'VIEW')) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="font-display txt text-[22px] font-extrabold">Custom Fields</h1>
        <p className="txt-muted mt-1 text-[13px]">
          You do not have permission to view this organization&apos;s field configuration.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-500 to-purple-600">
          <SlidersHorizontal className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Custom Fields</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            Fields your organization has added to its records, and the option lists they
            choose from.
          </p>
        </div>
      </div>

      <Tabs
        tabs={[
          { id: 'fields', label: 'Fields', content: <FieldsTab /> },
          { id: 'picklists', label: 'Picklists', content: <PicklistsTab /> },
        ]}
      />
    </div>
  );
}

/* ------------------------------------------------------------------
   Fields
   ------------------------------------------------------------------ */

function FieldsTab() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('custom_fields', 'CREATE');
  const mayEdit = can('custom_fields', 'EDIT');
  const mayDelete = can('custom_fields', 'DELETE');

  const [entityType, setEntityType] = useState<CustomFieldEntityType>('LEAD');
  const [fields, setFields] = useState<CustomFieldDefinition[] | null>(null);
  const [picklists, setPicklists] = useState<Picklist[]>([]);
  const [error, setError] = useState<string | null>(null);

  // A counter rather than a callback that fetches: reloading has to be
  // expressible as a *state change* so the fetch itself stays inside the
  // effect. Assigning state synchronously in an effect body cascades an extra
  // render pass, which is what `useCollection` avoids the same way.
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        // Both in flight at once: the drawer's picklist select needs the
        // lists, and neither request depends on the other's result.
        const [definitions, lists] = await Promise.all([
          listCustomFields({ entity_type: entityType, include_inactive: true }),
          listPicklists({ page_size: 200, sort_by: 'name', sort_dir: 'asc' }),
        ]);
        if (cancelled) return;
        setFields(definitions);
        setPicklists(lists.data);
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setFields([]);
        setError(describeApiError(caught, 'Custom fields could not be loaded.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [entityType, attempt]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<CustomFieldDefinition | null>(null);
  const [form, setForm] = useState<CustomFieldInput>(EMPTY_FIELD);
  const { pending, error: saveError, clearError, run } = useMutation();

  const openAdd = () => {
    setEditing(null);
    setForm({ ...EMPTY_FIELD, entity_type: entityType });
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (field: CustomFieldDefinition) => {
    setEditing(field);
    setForm({
      entity_type: field.entity_type,
      api_name: field.api_name,
      label: field.label,
      field_type: field.field_type,
      help_text: field.help_text ?? '',
      is_required: field.is_required,
      is_active: field.is_active,
      default_value: field.default_value ?? '',
      picklist_id: field.picklist_id,
      min_value: field.min_value,
      max_value: field.max_value,
      min_length: field.min_length,
      max_length: field.max_length,
      pattern: field.pattern ?? '',
    });
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    if (!form.label.trim()) return;
    const shared = {
      label: form.label.trim(),
      help_text: form.help_text?.trim() || null,
      is_required: form.is_required,
      is_active: form.is_active,
      default_value: form.default_value?.trim() || null,
      picklist_id: isPicklistType(form.field_type) ? form.picklist_id : null,
      pattern: form.pattern?.trim() || null,
    };
    const saved = await run(() =>
      editing
        ? updateCustomField(editing.id, shared)
        : createCustomField({
            ...shared,
            entity_type: form.entity_type,
            // Derived from the label when none was typed, which is what an
            // administrator means in practice: the machine name exists because
            // the storage needs one, not because they wanted to choose it.
            api_name: form.api_name.trim() || slugify(form.label),
            field_type: form.field_type,
          }),
    );
    if (saved === undefined) return; // the drawer stays open and shows the error
    setDrawerOpen(false);
    notifySuccess(editing ? 'Field updated' : 'Field created', shared.label);
    reload();
  };

  const handleArchive = async (field: CustomFieldDefinition) => {
    const ok = await confirm({
      title: `Remove ${field.label}?`,
      description:
        'It stops being offered on forms and stops being validated. Values already stored on records are kept, not deleted, so nothing collected through it is lost.',
      confirmLabel: 'Remove field',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveCustomField(field.id);
      notifySuccess('Field removed', field.label);
      reload();
    } catch (caught) {
      notifyError(caught, 'The field could not be removed.');
    }
  };

  const move = async (index: number, delta: number) => {
    if (!fields) return;
    const next = [...fields];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    // Painted first, then confirmed: this is the one action here where a round
    // trip's latency would read as lag. A failure reloads the real order.
    setFields(next);
    try {
      await reorderCustomFields(
        entityType,
        next.map((field) => field.id),
      );
    } catch (caught) {
      notifyError(caught, 'The order could not be saved.');
      reload();
    }
  };

  const picklistName = useMemo(
    () => new Map(picklists.map((list) => [list.id, list.name])),
    [picklists],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <FormSelect
          aria-label="Record type"
          value={entityType}
          onChange={(event) => setEntityType(event.target.value as CustomFieldEntityType)}
          options={ENTITY_OPTIONS}
          className="max-w-[220px]"
        />
        {mayCreate && (
          <button
            type="button"
            onClick={openAdd}
            className="ml-auto flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <Plus className="h-4 w-4" /> New field
          </button>
        )}
      </div>

      {error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : fields === null ? (
        <Loader2 className="txt-faint h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
      ) : fields.length === 0 ? (
        <p className="txt-muted text-[13px]">
          No custom fields on {titleCase(entityType)} records yet.
        </p>
      ) : (
        <ul className="space-y-2" data-testid="custom-field-list">
          {fields.map((field, index) => (
            <li
              key={field.id}
              className="ctl flex flex-wrap items-center gap-3 rounded-lg px-4 py-3"
            >
              <div className="flex flex-col gap-0.5">
                <button
                  type="button"
                  aria-label={`Move ${field.label} up`}
                  disabled={index === 0 || !mayEdit}
                  onClick={() => void move(index, -1)}
                  className="txt-faint transition hover:opacity-70 disabled:opacity-25"
                >
                  <ChevronUp className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  aria-label={`Move ${field.label} down`}
                  disabled={index === fields.length - 1 || !mayEdit}
                  onClick={() => void move(index, 1)}
                  className="txt-faint transition hover:opacity-70 disabled:opacity-25"
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="min-w-0 flex-1">
                <p className="txt text-[13px] font-semibold">
                  {field.label}
                  {field.is_required && <span className="ml-0.5 text-red-500">*</span>}
                </p>
                <p className="txt-faint truncate text-[11px]">
                  <code>{field.api_name}</code> · {titleCase(field.field_type)}
                  {field.picklist_id
                    ? ` · ${picklistName.get(field.picklist_id) ?? 'picklist'}`
                    : ''}
                </p>
              </div>
              <StatusBadge
                label={field.is_active ? 'Active' : 'Inactive'}
                variant={field.is_active ? 'success' : 'neutral'}
              />
              <div className="flex items-center gap-1">
                {mayEdit && (
                  <button
                    type="button"
                    aria-label={`Edit ${field.label}`}
                    onClick={() => openEdit(field)}
                    className="ctl rounded-lg p-1.5 transition hover:opacity-70"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
                {mayDelete && (
                  <button
                    type="button"
                    aria-label={`Remove ${field.label}`}
                    onClick={() => void handleArchive(field)}
                    className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? `Edit ${editing.label}` : 'New custom field'}
        footer={
          <DrawerActions
            onCancel={() => setDrawerOpen(false)}
            onSubmit={() => void handleSave()}
            label={editing ? 'Save field' : 'Create field'}
            pending={pending}
          />
        }
      >
        <div className="space-y-4">
          <FormError message={saveError} />

          <FormField label="Label" required>
            <FormInput
              value={form.label}
              onChange={(event) => setForm({ ...form, label: event.target.value })}
              placeholder="Territory"
            />
          </FormField>

          {editing ? (
            <p className="txt-faint text-[12px]">
              API name <code>{editing.api_name}</code> and type{' '}
              <strong>{titleCase(editing.field_type)}</strong> cannot be changed — records
              store their values under them. To change either, remove this field and add a
              new one.
            </p>
          ) : (
            <>
              <FormField
                label="API name"
                hint="Used in exports, imports and filters. Left blank, it is derived from the label. It cannot be changed later."
              >
                <FormInput
                  value={form.api_name}
                  onChange={(event) => setForm({ ...form, api_name: event.target.value })}
                  placeholder={slugify(form.label) || 'territory'}
                />
              </FormField>

              <FormField label="Record type" required>
                <FormSelect
                  value={form.entity_type}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      entity_type: event.target.value as CustomFieldEntityType,
                    })
                  }
                  options={ENTITY_OPTIONS}
                />
              </FormField>

              <FormField label="Type" required>
                <FormSelect
                  value={form.field_type}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      field_type: event.target.value as CustomFieldType,
                      // Cleared on a type change: a picklist chosen for a
                      // PICKLIST field is refused outright on a TEXT one.
                      picklist_id: null,
                    })
                  }
                  options={TYPE_OPTIONS}
                />
              </FormField>
            </>
          )}

          {isPicklistType(form.field_type) && (
            <FormField
              label="Picklist"
              required
              hint="The option set this field offers. Create one on the Picklists tab first."
            >
              <FormSelect
                value={form.picklist_id ?? ''}
                onChange={(event) =>
                  setForm({ ...form, picklist_id: event.target.value || null })
                }
                placeholder="Choose a picklist…"
                options={picklists.map((list) => ({ value: list.id, label: list.name }))}
              />
            </FormField>
          )}

          <FormField label="Help text" hint="Shown under the input on record forms.">
            <FormTextarea
              rows={2}
              value={form.help_text ?? ''}
              onChange={(event) => setForm({ ...form, help_text: event.target.value })}
            />
          </FormField>

          <FormField
            label="Default value"
            hint="Applied to new records that leave the field blank."
          >
            <FormInput
              value={form.default_value ?? ''}
              onChange={(event) => setForm({ ...form, default_value: event.target.value })}
            />
          </FormField>

          <label className="flex items-center gap-2 text-[13px]">
            <input
              type="checkbox"
              checked={form.is_required ?? false}
              onChange={(event) => setForm({ ...form, is_required: event.target.checked })}
              className="h-4 w-4"
            />
            <span className="txt font-semibold">Required</span>
          </label>

          <label className="flex items-start gap-2 text-[13px]">
            <input
              type="checkbox"
              checked={form.is_active ?? true}
              onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
              className="mt-0.5 h-4 w-4"
            />
            <span>
              <span className="txt font-semibold">Active</span>
              <span className="txt-faint block text-[11px]">
                Inactive fields are hidden from forms; stored values are kept.
              </span>
            </span>
          </label>
        </div>
      </SlideDrawer>
    </div>
  );
}

/* ------------------------------------------------------------------
   Picklists
   ------------------------------------------------------------------ */

function PicklistsTab() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('custom_fields', 'CREATE');
  const mayEdit = can('custom_fields', 'EDIT');
  const mayDelete = can('custom_fields', 'DELETE');

  const [lists, setLists] = useState<Picklist[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [options, setOptions] = useState<Record<string, PicklistOption[]>>({});

  // See the Fields tab: reload is a state change so the fetch stays inside
  // the effect.
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const page = await listPicklists({
          page_size: 200,
          sort_by: 'name',
          sort_dir: 'asc',
        });
        if (cancelled) return;
        setLists(page.data);
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setLists([]);
        setError(describeApiError(caught, 'Picklists could not be loaded.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const loadOptions = useCallback(async (listId: string) => {
    // Every option, active and inactive: this is the administration view,
    // where the point is to see and re-activate what was retired.
    const detail = await getPicklist(listId);
    setOptions((current) => ({ ...current, [listId]: detail.options ?? [] }));
  }, []);

  const toggle = async (list: Picklist) => {
    if (expanded === list.id) {
      setExpanded(null);
      return;
    }
    setExpanded(list.id);
    try {
      await loadOptions(list.id);
    } catch (caught) {
      notifyError(caught, 'The options could not be loaded.');
    }
  };

  const afterOptionChange = async (listId: string) => {
    try {
      await loadOptions(listId);
    } catch (caught) {
      notifyError(caught, 'The options could not be reloaded.');
    }
    // Reloads the list too, because `option_count` is on the row.
    reload();
  };

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [form, setForm] = useState({ name: '', api_name: '', description: '' });
  const { pending, error: saveError, clearError, run } = useMutation();

  const openAdd = () => {
    setForm({ name: '', api_name: '', description: '' });
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    const saved = await run(() =>
      createPicklist({
        name: form.name.trim(),
        api_name: form.api_name.trim() || slugify(form.name),
        description: form.description.trim() || null,
      }),
    );
    if (saved === undefined) return;
    setDrawerOpen(false);
    notifySuccess('Picklist created', form.name.trim());
    reload();
  };

  const handleArchive = async (list: Picklist) => {
    const ok = await confirm({
      title: `Remove ${list.name}?`,
      description:
        'Fields still drawing their options from this list will block the removal, and the message will name them.',
      confirmLabel: 'Remove picklist',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archivePicklist(list.id);
      notifySuccess('Picklist removed', list.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The picklist could not be removed.');
    }
  };

  return (
    <div className="space-y-4">
      {mayCreate && (
        <div className="flex">
          <button
            type="button"
            onClick={openAdd}
            className="ml-auto flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <Plus className="h-4 w-4" /> New picklist
          </button>
        </div>
      )}

      {error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : lists === null ? (
        <Loader2 className="txt-faint h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
      ) : lists.length === 0 ? (
        <p className="txt-muted text-[13px]">No picklists yet.</p>
      ) : (
        <ul className="space-y-2" data-testid="picklist-list">
          {lists.map((list) => (
            <li key={list.id} className="ctl rounded-lg px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void toggle(list)}
                  className="min-w-0 flex-1 text-left"
                  aria-expanded={expanded === list.id}
                >
                  <p className="txt text-[13px] font-semibold">{list.name}</p>
                  <p className="txt-faint text-[11px]">
                    <code>{list.api_name}</code> · {list.option_count} option
                    {list.option_count === 1 ? '' : 's'}
                  </p>
                </button>
                {mayDelete && (
                  <button
                    type="button"
                    aria-label={`Remove ${list.name}`}
                    onClick={() => void handleArchive(list)}
                    className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {expanded === list.id && (
                <PicklistOptions
                  list={list}
                  options={options[list.id] ?? []}
                  mayEdit={mayEdit}
                  onChanged={() => void afterOptionChange(list.id)}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="New picklist"
        footer={
          <DrawerActions
            onCancel={() => setDrawerOpen(false)}
            onSubmit={() => void handleSave()}
            label="Create picklist"
            pending={pending}
          />
        }
      >
        <div className="space-y-4">
          <FormError message={saveError} />
          <FormField label="Name" required>
            <FormInput
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Region"
            />
          </FormField>
          <FormField
            label="API name"
            hint="Left blank, it is derived from the name. It cannot be changed later."
          >
            <FormInput
              value={form.api_name}
              onChange={(event) => setForm({ ...form, api_name: event.target.value })}
              placeholder={slugify(form.name) || 'region'}
            />
          </FormField>
          <FormField label="Description">
            <FormTextarea
              rows={2}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </FormField>
        </div>
      </SlideDrawer>
    </div>
  );
}

function PicklistOptions({
  list,
  options,
  mayEdit,
  onChanged,
}: {
  list: Picklist;
  options: PicklistOption[];
  mayEdit: boolean;
  onChanged: () => void;
}) {
  const [value, setValue] = useState('');

  const add = async () => {
    if (!value.trim()) return;
    try {
      await addPicklistOption(list.id, { value: value.trim(), position: options.length });
      setValue('');
      onChanged();
    } catch (caught) {
      notifyError(caught, 'The option could not be added.');
    }
  };

  const setActive = async (option: PicklistOption, isActive: boolean) => {
    try {
      await updatePicklistOption(list.id, option.id, { is_active: isActive });
      onChanged();
    } catch (caught) {
      notifyError(caught, 'The option could not be updated.');
    }
  };

  const remove = async (option: PicklistOption) => {
    try {
      await removePicklistOption(list.id, option.id);
      onChanged();
    } catch (caught) {
      notifyError(caught, 'The option could not be removed.');
    }
  };

  return (
    <div className="bd mt-3 space-y-2 border-t pt-3">
      {options.length === 0 && <p className="txt-faint text-[12px]">No options yet.</p>}
      {options.map((option) => (
        <div key={option.id} className="flex flex-wrap items-center gap-2 text-[12px]">
          <ListChecks className="txt-faint h-3.5 w-3.5" aria-hidden="true" />
          <span className="txt font-medium">{option.label}</span>
          <code className="txt-faint">{option.value}</code>
          {option.is_default && <StatusBadge label="Default" variant="accent" />}
          {!option.is_active && <StatusBadge label="Inactive" variant="neutral" />}
          {mayEdit && (
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={() => void setActive(option, !option.is_active)}
                className="txt-faint text-[11px] underline transition hover:opacity-70"
              >
                {option.is_active ? 'Deactivate' : 'Reactivate'}
              </button>
              <button
                type="button"
                aria-label={`Remove ${option.label}`}
                onClick={() => void remove(option)}
                className="ctl rounded-lg p-1 text-red-500 transition hover:opacity-70"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
      ))}
      {mayEdit && (
        <div className="flex items-center gap-2 pt-1">
          <FormInput
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Add an option…"
            aria-label={`Add an option to ${list.name}`}
            className="max-w-[240px]"
          />
          <button
            type="button"
            onClick={() => void add()}
            className="rounded-lg px-3 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            Add
          </button>
        </div>
      )}
      <p className="txt-faint pt-1 text-[11px]">
        Deactivating or removing an option stops it being offered. Records already holding it
        keep the value.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------
   Helpers
   ------------------------------------------------------------------ */

function DrawerActions({
  onCancel,
  onSubmit,
  label,
  pending,
}: {
  onCancel: () => void;
  onSubmit: () => void;
  label: string;
  pending: boolean;
}) {
  return (
    <div className="flex justify-end gap-2">
      <button
        type="button"
        onClick={onCancel}
        className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
      >
        Cancel
      </button>
      <button
        type="button"
        onClick={onSubmit}
        disabled={pending}
        className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
        style={{ background: 'var(--accent)' }}
      >
        {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
        {label}
      </button>
    </div>
  );
}

/**
 * Derive a machine name from a label.
 *
 * Matches what the backend accepts (`^[a-z][a-z0-9_]{0,63}$`) rather than
 * being a general-purpose slugifier, so what this produces is never a value
 * the API will reject. A label starting with a digit gets an `f_` prefix for
 * the same reason.
 */
function slugify(label: string): string {
  const base = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
  if (!base) return '';
  return /^[a-z]/.test(base) ? base : `f_${base}`.slice(0, 64);
}

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
