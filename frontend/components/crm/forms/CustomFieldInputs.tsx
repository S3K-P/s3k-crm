'use client';

import { useCallback, useEffect, useState } from 'react';

import FormField from '@/components/crm/forms/FormField';
import {
  getEntitySchema,
  isPicklistType,
  type CustomFieldDefinition,
  type CustomFieldEntityType,
  type CustomFieldValue,
  type CustomFieldValues,
} from '@/features/crm/custom-fields';
import { effectiveFieldStates } from '@/features/crm/layouts/evaluate';
import { asLayoutEntityType, customFieldKey, isCustomFieldKey, type LayoutField } from '@/features/crm/layouts';
import { usePublishedLayout } from '@/features/crm/layouts/usePublishedLayout';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { cn } from '@/lib/utils';

/* ============================================================
   CUSTOM FIELD INPUTS

   Renders the tenant-defined half of a record form from the
   definitions the backend supplies, and nothing else.

   Three decisions worth stating, because each has a wrong
   version that looks fine until it does not:

   - **The schema is fetched, never assumed.** Which fields exist
     is tenant data. Any list compiled into this file would be
     one customer's configuration shown to everybody.
   - **Validation is not duplicated here.** `required`, `min`,
     `max` and `pattern` are passed to the browser so the user
     gets an instant hint, but the backend is what decides, and
     its 422 is what the form reports. Re-implementing the rules
     in TypeScript would give two answers that drift.
   - **A retired field is absent, not disabled.** The schema
     endpoint excludes inactive fields, so a form drawn from it
     cannot offer one — which is why this component does not
     filter on `is_active` itself and would be wrong to.

   A failure to load leaves the section out with a message rather
   than blocking the whole form: a rep must still be able to save
   a lead's name when the custom-field endpoint is unhappy.
   ============================================================ */

interface CustomFieldInputsProps {
  entityType: CustomFieldEntityType;
  values: CustomFieldValues;
  onChange: (values: CustomFieldValues) => void;
  /** Field-level messages from a backend 422, keyed by `api_name`. */
  errors?: Record<string, string>;
  disabled?: boolean;
  className?: string;
  /**
   * The rest of the record's current field values (built-in columns, plus
   * these same custom values) — Checkpoint 4. Feeds a published layout's
   * conditional rules, so "IF Lead Status = Qualified THEN show Qualification
   * Details" can react as the user edits either field, live.
   *
   * Optional and additive: omitted, this component renders exactly as it did
   * before layouts existed. Supplied with no published layout for
   * `entityType`, it is read but changes nothing — there are no rules to
   * evaluate. This is never the authority on what is actually required; the
   * same evaluation runs again, server-side, on the real write. See
   * `features/crm/layouts/evaluate.ts`.
   */
  recordContext?: Record<string, unknown>;
}

export default function CustomFieldInputs({
  entityType,
  values,
  onChange,
  errors,
  disabled,
  className,
  recordContext,
}: CustomFieldInputsProps) {
  const { fields, status, error } = useEntitySchema(entityType);
  const { layout } = usePublishedLayout(asLayoutEntityType(entityType));

  const set = useCallback(
    (apiName: string, value: CustomFieldValue) => onChange({ ...values, [apiName]: value }),
    [onChange, values],
  );

  if (status === 'loading' || (status === 'ready' && fields.length === 0)) return null;

  if (status === 'error') {
    return (
      <p className="txt-faint text-[12px]" role="status">
        Custom fields could not be loaded: {error}
      </p>
    );
  }

  const placedByKey = new Map<string, LayoutField>();
  if (layout) {
    for (const section of layout.sections) {
      for (const field of section.fields) {
        if (isCustomFieldKey(field.field_key)) placedByKey.set(field.field_key, field);
      }
    }
  }

  // Base state before any rule is applied: a placed field's own
  // `is_required_override`/`is_visible`, falling back to the definition's own
  // `is_required` — the identical precedence the backend resolves, restated
  // here only so the live preview does not disagree with it.
  const baseVisible: Record<string, boolean> = {};
  const baseRequired: Record<string, boolean> = {};
  for (const field of fields) {
    const key = customFieldKey(field.api_name);
    const placed = placedByKey.get(key);
    if (!placed) continue;
    baseVisible[key] = placed.is_visible;
    baseRequired[key] = placed.is_required_override ?? field.is_required;
  }

  const context = { ...recordContext, ...values };
  const states =
    layout && layout.rules.length > 0
      ? effectiveFieldStates(layout.rules, context, baseVisible, baseRequired)
      : {};

  const ordered = layout
    ? [...fields].sort((a, b) => {
        const posA = placedByKey.get(customFieldKey(a.api_name))?.position;
        const posB = placedByKey.get(customFieldKey(b.api_name))?.position;
        if (posA !== undefined && posB !== undefined) return posA - posB;
        if (posA !== undefined) return -1;
        if (posB !== undefined) return 1;
        return 0;
      })
    : fields;

  return (
    <div className={cn('space-y-4', className)} data-testid="custom-fields">
      {ordered.map((field) => {
        const key = customFieldKey(field.api_name);
        const placed = placedByKey.get(key);
        const state = states[key];
        if (state && !state.visible) return null;

        const effective: CustomFieldDefinition = placed
          ? {
              ...field,
              label: placed.label_override ?? field.label,
              help_text: placed.help_text_override ?? field.help_text,
              is_required: state ? (state.required ?? false) : baseRequired[key] ?? field.is_required,
            }
          : field;

        return (
          <CustomFieldControl
            key={field.id}
            field={effective}
            placeholder={placed?.placeholder_override ?? undefined}
            value={values[field.api_name] ?? (field.field_type === 'MULTI_PICKLIST' ? [] : '')}
            onChange={(value) => set(field.api_name, value)}
            error={errors?.[field.api_name]}
            disabled={disabled || (placed?.is_read_only ?? false)}
          />
        );
      })}
    </div>
  );
}

/** One control, chosen by the definition's declared type. */
function CustomFieldControl({
  field,
  value,
  onChange,
  error,
  disabled,
  placeholder,
}: {
  field: CustomFieldDefinition;
  value: CustomFieldValue;
  onChange: (value: CustomFieldValue) => void;
  error?: string;
  disabled?: boolean;
  /** A layout field's placeholder override (Checkpoint 4). */
  placeholder?: string;
}) {
  const common = {
    name: `cf_${field.api_name}`,
    disabled,
    required: field.is_required,
    placeholder,
    'data-testid': `cf-${field.api_name}`,
  };

  if (field.field_type === 'BOOLEAN') {
    // Checkboxes get their own layout: `FormField` puts the label above the
    // control, which reads as a stray tick box under a heading.
    return (
      <label className="flex items-center gap-2 text-[13px]">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
          className="h-4 w-4"
          {...common}
        />
        <span className="txt font-semibold">{field.label}</span>
        {field.help_text && <span className="txt-faint">{field.help_text}</span>}
      </label>
    );
  }

  return (
    <FormField
      label={field.label}
      required={field.is_required}
      hint={field.help_text ?? undefined}
      error={error}
    >
      {renderControl(field, value, onChange, common)}
    </FormField>
  );
}

function renderControl(
  field: CustomFieldDefinition,
  value: CustomFieldValue,
  onChange: (value: CustomFieldValue) => void,
  common: Record<string, unknown>,
) {
  const options = field.options ?? [];

  if (field.field_type === 'MULTI_PICKLIST') {
    const selected = Array.isArray(value) ? value : [];
    return (
      <select
        multiple
        className="ctl w-full px-3 py-2 text-[13px]"
        value={selected}
        onChange={(event) =>
          onChange(Array.from(event.target.selectedOptions, (option) => option.value))
        }
        {...common}
      >
        {options.map((option) => (
          <option key={option.id} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (isPicklistType(field.field_type)) {
    const current = typeof value === 'string' ? value : '';
    // A value whose option has been retired is added back as a disabled entry,
    // so opening the form does not silently blank a field the record holds.
    const missing = current && !options.some((option) => option.value === current);
    return (
      <select
        className="ctl w-full px-3 py-2 text-[13px]"
        value={current}
        onChange={(event) => onChange(event.target.value)}
        {...common}
      >
        <option value="">—</option>
        {missing && (
          <option value={current} disabled>
            {current} (no longer available)
          </option>
        )}
        {options.map((option) => (
          <option key={option.id} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.field_type === 'TEXTAREA') {
    return (
      <textarea
        className="ctl w-full px-3 py-2 text-[13px]"
        rows={3}
        value={typeof value === 'string' ? value : ''}
        maxLength={field.max_length ?? undefined}
        minLength={field.min_length ?? undefined}
        onChange={(event) => onChange(event.target.value)}
        {...common}
      />
    );
  }

  return (
    <input
      className="ctl w-full px-3 py-2 text-[13px]"
      type={inputType(field)}
      value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
      onChange={(event) => onChange(event.target.value)}
      // Passed through so the browser can hint early. The backend still
      // decides; these are a convenience, not the rule.
      min={field.min_value ?? undefined}
      max={field.max_value ?? undefined}
      minLength={field.min_length ?? undefined}
      maxLength={field.max_length ?? undefined}
      pattern={field.pattern ?? undefined}
      step={field.field_type === 'DECIMAL' ? 'any' : undefined}
      {...common}
    />
  );
}

function inputType(field: CustomFieldDefinition): string {
  switch (field.field_type) {
    case 'NUMBER':
    case 'DECIMAL':
      return 'number';
    case 'DATE':
      return 'date';
    case 'DATETIME':
      return 'datetime-local';
    case 'EMAIL':
      return 'email';
    case 'URL':
      return 'url';
    case 'PHONE':
      return 'tel';
    default:
      return 'text';
  }
}

/* ------------------------------------------------------------------
   Schema loading
   ------------------------------------------------------------------ */

interface SchemaState {
  fields: CustomFieldDefinition[];
  status: 'loading' | 'ready' | 'error';
  error: string | null;
}

/** What one completed load produced, stamped with the request it answered. */
interface SchemaResult {
  entityType: CustomFieldEntityType;
  fields: CustomFieldDefinition[];
  error: string | null;
}

/**
 * Load one record type's active custom fields.
 *
 * The result is stamped with the `entityType` it answered and compared against
 * the one being rendered, rather than a "loading" flag being set when the
 * effect starts. Two things fall out of that, and both matter:
 *
 * - A late response for a *previous* entity type cannot repaint the form with
 *   the wrong fields — the same correctness property `useCollection` exists to
 *   hold for list screens.
 * - Nothing calls `setState` synchronously inside the effect, so switching
 *   record type does not cascade an extra render pass.
 */
export function useEntitySchema(entityType: CustomFieldEntityType): SchemaState {
  const [result, setResult] = useState<SchemaResult | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const schema = await getEntitySchema(entityType);
        if (!cancelled) setResult({ entityType, fields: schema.fields, error: null });
      } catch (caught) {
        if (!cancelled) {
          setResult({
            entityType,
            fields: [],
            error: describeApiError(caught, 'Could not load custom fields.'),
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [entityType]);

  const current = result?.entityType === entityType ? result : null;
  if (current === null) return { fields: [], status: 'loading', error: null };
  if (current.error !== null) {
    return { fields: [], status: 'error', error: current.error };
  }
  return { fields: current.fields, status: 'ready', error: null };
}
