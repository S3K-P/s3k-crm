'use client';

import { useEntitySchema } from '@/components/crm/forms/CustomFieldInputs';
import {
  describeValue,
  type CustomFieldEntityType,
  type CustomFieldValues,
} from '@/features/crm/custom-fields';

/* ============================================================
   CUSTOM FIELDS PANEL

   The read-only half: a record's tenant-defined values on its
   detail page.

   Renders in definition order rather than in whatever order the
   JSON document happens to hold, so the detail page and the edit
   form agree about where a field is.

   A value stored under a field that has since been **retired**
   is shown too, in its own group. The data is still on the
   record and hiding it would make it look deleted — which it is
   not, and which is exactly what the storage design set out to
   avoid. It is labelled so nobody mistakes it for a live field.

   Nothing renders when the tenant has defined no fields — not
   even the card, which is why the card lives here rather than on
   the pages. A wrapper on the page would leave an empty bordered
   box on every detail screen of every organization that has not
   used the feature.
   ============================================================ */

interface CustomFieldsPanelProps {
  entityType: CustomFieldEntityType;
  values: CustomFieldValues | undefined;
}

export default function CustomFieldsPanel({ entityType, values }: CustomFieldsPanelProps) {
  const { fields, status } = useEntitySchema(entityType);
  const document = values ?? {};

  if (status !== 'ready') return null;

  const known = new Set(fields.map((field) => field.api_name));
  const orphaned = Object.keys(document).filter((key) => !known.has(key));

  if (fields.length === 0 && orphaned.length === 0) return null;

  return (
    <section
      className="surface bd space-y-3 rounded-2xl border p-5"
      data-testid="custom-fields-panel"
    >
      <h3 className="txt font-display text-[16px] font-bold">Additional information</h3>
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {fields.map((field) => (
          <div key={field.id}>
            <dt className="txt-faint text-[11px] font-medium uppercase tracking-wide">
              {field.label}
            </dt>
            <dd className="txt text-[13px]">
              {describeValue(field, document[field.api_name] ?? null)}
            </dd>
          </div>
        ))}
        {orphaned.map((key) => (
          <div key={key}>
            <dt className="txt-faint text-[11px] font-medium uppercase tracking-wide">
              {key} <span className="normal-case">(retired field)</span>
            </dt>
            <dd className="txt text-[13px]">{formatRaw(document[key])}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/**
 * A value with no definition left to interpret it.
 *
 * There is no option list to resolve a label against and no declared type to
 * format by, so this shows the stored value as plainly as possible rather than
 * guessing.
 */
function formatRaw(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}
