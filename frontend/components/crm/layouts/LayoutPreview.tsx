'use client';

import { useEffect, useMemo, useState } from 'react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { getEntitySchema, isPicklistType, type CustomFieldDefinition } from '@/features/crm/custom-fields';
import { effectiveFieldStates } from '@/features/crm/layouts/evaluate';
import { customFieldApiName, isCustomFieldKey, type LayoutField, type RecordLayoutDetail } from '@/features/crm/layouts';

/* ============================================================
   LAYOUT PREVIEW

   A live, honest mock of the form this layout produces — honest
   because it is built from the same data the real form is (the
   layout's own sections/fields and, for custom fields, the real
   field definitions), not a static illustration. Typing a value
   into any field re-evaluates every conditional rule immediately,
   using the identical `evaluate.ts` the real form's
   `CustomFieldInputs` also calls, so what an administrator sees
   here is what a rep will see.

   A built-in field renders as a plain labelled text input: this
   preview does not know a lead's `status` is an enum with five
   legal values, only that a layout placed a field called
   `status` — real built-in rendering lives in each entity's own
   page, unchanged by Checkpoint 4. Typing into one still drives
   conditional rules exactly as it would on the real form.
   ============================================================ */

export default function LayoutPreview({
  layout,
  onClose,
}: {
  layout: RecordLayoutDetail;
  onClose: () => void;
}) {
  const [definitions, setDefinitions] = useState<CustomFieldDefinition[] | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const schema = await getEntitySchema(layout.entity_type);
        if (!cancelled) setDefinitions(schema.fields);
      } catch {
        if (!cancelled) setDefinitions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [layout.entity_type]);

  const definitionByApiName = useMemo(() => {
    const map = new Map<string, CustomFieldDefinition>();
    for (const def of definitions ?? []) map.set(def.api_name, def);
    return map;
  }, [definitions]);

  const baseVisible: Record<string, boolean> = {};
  const baseRequired: Record<string, boolean> = {};
  for (const section of layout.sections) {
    for (const field of section.fields) {
      if (!isCustomFieldKey(field.field_key)) continue;
      baseVisible[field.field_key] = field.is_visible;
      const definition = definitionByApiName.get(customFieldApiName(field.field_key));
      baseRequired[field.field_key] = field.is_required_override ?? definition?.is_required ?? false;
    }
  }
  const states = effectiveFieldStates(layout.rules, values, baseVisible, baseRequired);

  function set(fieldKey: string, value: string) {
    setValues((prev) => ({ ...prev, [fieldKey]: value }));
  }

  return (
    <SlideDrawer open onClose={onClose} title={`Preview — ${layout.name}`} width="max-w-2xl">
      <div className="space-y-5">
        <p className="txt-faint text-[11.5px]">
          Type into any field to see conditional rules react, exactly as the real form will.
        </p>
        {layout.sections.map((section) => (
          <div key={section.id} className="bd surface rounded-xl border p-4">
            <h3 className="txt mb-3 text-[13px] font-semibold">{section.name}</h3>
            <div className={section.columns === 2 ? 'grid grid-cols-2 gap-3' : 'space-y-3'}>
              {section.fields.map((field) => (
                <PreviewField
                  key={field.id}
                  field={field}
                  definition={
                    isCustomFieldKey(field.field_key)
                      ? definitionByApiName.get(customFieldApiName(field.field_key))
                      : undefined
                  }
                  visible={states[field.field_key]?.visible ?? true}
                  required={states[field.field_key]?.required ?? field.is_required_override ?? false}
                  value={String(values[field.field_key] ?? '')}
                  onChange={(v) => set(field.field_key, v)}
                />
              ))}
            </div>
          </div>
        ))}
        {layout.sections.length === 0 && (
          <p className="txt-faint text-[13px]">This layout has no sections yet.</p>
        )}
      </div>
    </SlideDrawer>
  );
}

function PreviewField({
  field,
  definition,
  visible,
  required,
  value,
  onChange,
}: {
  field: LayoutField;
  definition?: CustomFieldDefinition;
  visible: boolean;
  required: boolean;
  value: string;
  onChange: (value: string) => void;
}) {
  if (!visible) return null;

  const label = field.label_override ?? definition?.label ?? field.field_key.replace('custom:', '');
  const help = field.help_text_override ?? definition?.help_text ?? undefined;

  return (
    <label
      className="block space-y-1"
      style={{ gridColumn: field.column_span === 2 ? 'span 2 / span 2' : undefined }}
    >
      <span className="txt block text-[12.5px] font-semibold">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </span>
      {definition && isPicklistType(definition.field_type) ? (
        <select
          className="ctl w-full px-3 py-2 text-[13px]"
          disabled={field.is_read_only}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">—</option>
          {definition.options?.map((option) => (
            <option key={option.id} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          className="ctl w-full px-3 py-2 text-[13px]"
          disabled={field.is_read_only}
          placeholder={field.placeholder_override ?? undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {help && <span className="txt-faint block text-[11px]">{help}</span>}
    </label>
  );
}
