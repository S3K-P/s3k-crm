'use client';

import { Plus, Trash2 } from 'lucide-react';

import {
  OPERATORS_BY_TYPE,
  OPERATOR_LABELS,
  RELATIVE_PERIODS,
  type AvailableFieldInfo,
  type ReportCondition,
  type ReportFilterGroup,
  type ReportFilterOperator,
} from '@/features/crm/reports/custom';

/* ============================================================
   FILTER EDITOR

   The AND/OR condition-group builder behind two features that
   share one vocabulary (Checkpoint 5): the custom-report
   builder's filter step (`ReportBuilder.tsx`) and a list
   screen's advanced filter (`AdvancedFilterBar.tsx`). Both send
   the exact same `ReportFilterGroup` shape to the backend —
   `reports.conditions.ReportFilterGroup` — so one editor is
   correct for both rather than two that could drift.
   ============================================================ */

const NEEDS_ONE_VALUE: ReadonlySet<ReportFilterOperator> = new Set([
  'eq', 'ne', 'contains', 'starts_with', 'ends_with', 'gt', 'gte', 'lt', 'lte',
]);

export function FilterEditor({
  group,
  fields,
  onChange,
}: {
  group: ReportFilterGroup;
  fields: AvailableFieldInfo[];
  onChange: (group: ReportFilterGroup) => void;
}) {
  const filterable = fields.filter(f => f.filterable);

  const add = () => {
    const first = filterable[0];
    if (!first) return;
    const op = OPERATORS_BY_TYPE[first.type][0];
    onChange({
      ...group,
      conditions: [...group.conditions, { field: first.key, operator: op, value: '' }],
    });
  };
  const update = (index: number, patch: Partial<ReportCondition>) => {
    onChange({
      ...group,
      conditions: group.conditions.map((c, i) => (i === index ? { ...c, ...patch } : c)),
    });
  };
  const remove = (index: number) => {
    onChange({ ...group, conditions: group.conditions.filter((_, i) => i !== index) });
  };

  return (
    <div className="space-y-2">
      {group.conditions.length > 1 && (
        <div className="flex items-center gap-2 text-[12px]">
          <span className="txt-faint">Match</span>
          <select
            value={group.logic}
            onChange={e => onChange({ ...group, logic: e.target.value as 'AND' | 'OR' })}
            className="ctl txt px-2 py-1 text-[12px]"
          >
            <option value="AND">all</option>
            <option value="OR">any</option>
          </select>
          <span className="txt-faint">of the following</span>
        </div>
      )}

      {group.conditions.map((condition, index) => {
        const field = fields.find(f => f.key === condition.field);
        const operators = field ? (OPERATORS_BY_TYPE[field.type] ?? []) : [];
        return (
          <div key={index} className="flex flex-wrap items-center gap-2">
            <select
              value={condition.field}
              onChange={e => {
                const next = fields.find(f => f.key === e.target.value);
                const op = next ? OPERATORS_BY_TYPE[next.type][0] : 'eq';
                update(index, { field: e.target.value, operator: op, value: '' });
              }}
              className="ctl txt px-2.5 py-1.5 text-[12.5px]"
            >
              {filterable.map(f => (
                <option key={f.key} value={f.key}>
                  {f.is_custom ? `${f.label} (custom)` : f.label}
                </option>
              ))}
            </select>
            <select
              value={condition.operator}
              onChange={e =>
                update(index, { operator: e.target.value as ReportFilterOperator, value: '' })
              }
              className="ctl txt px-2.5 py-1.5 text-[12.5px]"
            >
              {operators.map(op => (
                <option key={op} value={op}>
                  {OPERATOR_LABELS[op]}
                </option>
              ))}
            </select>
            <ConditionValue
              field={field}
              condition={condition}
              onChange={value => update(index, { value })}
            />
            <button
              type="button"
              onClick={() => remove(index)}
              aria-label="Remove condition"
              className="txt-faint hover:text-rose-500"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}

      <button
        type="button"
        onClick={add}
        disabled={filterable.length === 0}
        className="txt-faint hover:txt inline-flex items-center gap-1 text-[11.5px] font-semibold disabled:opacity-50"
      >
        <Plus className="h-3 w-3" /> Add a condition
      </button>
    </div>
  );
}

function ConditionValue({
  field,
  condition,
  onChange,
}: {
  field: AvailableFieldInfo | undefined;
  condition: ReportCondition;
  onChange: (value: unknown) => void;
}) {
  const operator = condition.operator;
  if (operator === 'is_empty' || operator === 'is_not_empty') return null;

  const inputType =
    field?.type === 'NUMBER' || field?.type === 'CURRENCY' || field?.type === 'PERCENT'
      ? 'number'
      : field?.type === 'DATE'
        ? 'date'
        : 'text';

  if (operator === 'between') {
    const [low, high] = Array.isArray(condition.value) ? condition.value : ['', ''];
    return (
      <div className="flex items-center gap-1.5">
        <input
          type={inputType}
          value={low ?? ''}
          onChange={e => onChange([e.target.value, high])}
          className="ctl txt w-24 px-2.5 py-1.5 text-[12.5px]"
        />
        <span className="txt-faint text-[11px]">and</span>
        <input
          type={inputType}
          value={high ?? ''}
          onChange={e => onChange([low, e.target.value])}
          className="ctl txt w-24 px-2.5 py-1.5 text-[12.5px]"
        />
      </div>
    );
  }

  if (operator === 'in') {
    return (
      <input
        type="text"
        placeholder="value1, value2, …"
        value={Array.isArray(condition.value) ? condition.value.join(', ') : (condition.value as string) ?? ''}
        onChange={e => onChange(e.target.value.split(',').map(v => v.trim()).filter(Boolean))}
        className="ctl txt w-40 px-2.5 py-1.5 text-[12.5px]"
      />
    );
  }

  if (field?.type === 'DATE') {
    const isRelative = typeof condition.value === 'object' && condition.value !== null;
    return (
      <div className="flex items-center gap-1.5">
        <select
          value={isRelative ? 'relative' : 'literal'}
          onChange={e =>
            onChange(e.target.value === 'relative' ? { relative: 'TODAY' } : '')
          }
          className="ctl txt px-2 py-1.5 text-[11.5px]"
        >
          <option value="literal">On date</option>
          <option value="relative">Relative</option>
        </select>
        {isRelative ? (
          <select
            value={(condition.value as { relative: string }).relative}
            onChange={e => onChange({ relative: e.target.value })}
            className="ctl txt px-2.5 py-1.5 text-[12.5px]"
          >
            {RELATIVE_PERIODS.map(p => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="date"
            value={(condition.value as string) ?? ''}
            onChange={e => onChange(e.target.value)}
            className="ctl txt px-2.5 py-1.5 text-[12.5px]"
          />
        )}
      </div>
    );
  }

  if (!NEEDS_ONE_VALUE.has(operator)) return null;

  return (
    <input
      type={inputType}
      value={(condition.value as string | number) ?? ''}
      onChange={e => onChange(inputType === 'number' ? Number(e.target.value) : e.target.value)}
      className="ctl txt w-32 px-2.5 py-1.5 text-[12.5px]"
    />
  );
}
