'use client';

import { useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Trash2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import { ListError } from '@/components/crm/shared/ListStates';
import { ReportChart, ReportTable, chartHasData } from '@/components/crm/reports/ReportView';
import { FilterEditor } from '@/components/crm/reports/FilterEditor';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import type { ReportResult } from '@/features/crm/reports';
import {
  AGG_LABELS,
  DATE_INTERVALS,
  EMPTY_CUSTOM_DEFINITION,
  REPORT_ENTITIES,
  listCustomFields,
  previewCustomReport,
  type AggOp,
  type AvailableFieldInfo,
  type ChartKind,
  type CustomReportDefinition,
  type ReportEntity,
} from '@/features/crm/reports/custom';

/* ============================================================
   REPORT BUILDER

   Choose module → fields or group+aggregate → filters → sort →
   chart → preview. One definition, the same shape the backend's
   custom-report engine validates and runs
   (`reports/custom.py`), so what this screen previews is
   exactly what a save persists and a dashboard tile later runs.

   Row-listing and grouped/aggregated are two different report
   shapes, not two settings of one report — switching toggles
   which controls below apply, matching the backend's own
   either/or validation (`CustomReportDefinition._shape_is_coherent`).
   ============================================================ */

function fieldsByKey(fields: AvailableFieldInfo[]): Map<string, AvailableFieldInfo> {
  return new Map(fields.map(f => [f.key, f]));
}

interface ReportBuilderProps {
  initial?: CustomReportDefinition;
  onSave: (definition: CustomReportDefinition, result: ReportResult) => void;
  onCancel: () => void;
  busy?: boolean;
  saveLabel?: string;
}

export default function ReportBuilder({
  initial,
  onSave,
  onCancel,
  busy = false,
  saveLabel = 'Save report',
}: ReportBuilderProps) {
  const [definition, setDefinition] = useState<CustomReportDefinition>(
    initial ?? EMPTY_CUSTOM_DEFINITION,
  );
  // Stamped with the entity it answers, and read against the *current*
  // entity below — never reset synchronously in the effect body, which is
  // what `react-hooks/set-state-in-effect` forbids. A response for an
  // entity the picker has since moved away from is simply not "current"
  // and is ignored at read time rather than raced against a reset.
  const [fieldsResult, setFieldsResult] = useState<
    | { entity: ReportEntity; fields: AvailableFieldInfo[]; error: null }
    | { entity: ReportEntity; fields: null; error: string }
    | null
  >(null);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const fields = fieldsResult?.entity === definition.entity ? fieldsResult.fields : null;
  const fieldsError = fieldsResult?.entity === definition.entity ? fieldsResult.error : null;

  const grouped = definition.group_by !== null && definition.group_by !== undefined;
  const byKey = useMemo(() => fieldsByKey(fields ?? []), [fields]);
  const builtinFields = useMemo(() => (fields ?? []).filter(f => !f.is_custom), [fields]);
  const groupableFields = useMemo(() => builtinFields.filter(f => f.groupable), [builtinFields]);

  // Bumped to re-run the effect below for the *same* entity — changing
  // `definition.entity` to a value it already holds would not, since that
  // is the effect's only other dependency.
  const [fieldsReloadKey, setFieldsReloadKey] = useState(0);

  /* --- Load the field registry whenever the entity changes ----------- */
  useEffect(() => {
    let cancelled = false;
    const entity = definition.entity;
    listCustomFields(entity)
      .then(list => {
        if (!cancelled) setFieldsResult({ entity, fields: list, error: null });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setFieldsResult({
            entity,
            fields: null,
            error: describeApiError(cause, 'Unable to load fields.'),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [definition.entity, fieldsReloadKey]);

  const setEntity = (entity: ReportEntity) => {
    setDefinition({ ...EMPTY_CUSTOM_DEFINITION, entity });
    setResult(null);
  };

  const setMode = (next: 'listing' | 'grouped') => {
    if (next === 'grouped') {
      setDefinition(d => ({ ...d, fields: [], group_by: groupableFields[0]?.key ?? null }));
    } else {
      setDefinition(d => ({
        ...d,
        group_by: null,
        group_by_interval: null,
        aggregations: [],
        chart_kind: null,
      }));
    }
    setResult(null);
  };

  const toggleField = (key: string) => {
    setDefinition(d => ({
      ...d,
      fields: d.fields.includes(key) ? d.fields.filter(f => f !== key) : [...d.fields, key],
    }));
  };

  const runPreview = async () => {
    setPreviewing(true);
    setPreviewError(null);
    try {
      setResult(await previewCustomReport(definition));
    } catch (cause) {
      setResult(null);
      setPreviewError(describeApiError(cause, 'Unable to run this report.'));
    } finally {
      setPreviewing(false);
    }
  };

  const canPreview = grouped
    ? definition.group_by !== null && definition.aggregations.length > 0
    : definition.fields.length > 0;

  return (
    <div className="space-y-5">
      <Field label="Module">
        <select
          value={definition.entity}
          onChange={e => setEntity(e.target.value as ReportEntity)}
          className="ctl txt w-full px-3 py-2 text-[13px]"
        >
          {REPORT_ENTITIES.map(e => (
            <option key={e.value} value={e.value}>
              {e.label}
            </option>
          ))}
        </select>
      </Field>

      {fieldsError && (
        <ListError message={fieldsError} onRetry={() => setFieldsReloadKey(key => key + 1)} />
      )}

      {fields && (
        <>
          <Field label="Shape">
            <div className="flex gap-2">
              <ModeButton active={!grouped} onClick={() => setMode('listing')}>
                Row listing
              </ModeButton>
              <ModeButton active={grouped} onClick={() => setMode('grouped')}>
                Group &amp; summarise
              </ModeButton>
            </div>
          </Field>

          {!grouped && (
            <Field label="Fields to show">
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {builtinFields.map(f => (
                  <label key={f.key} className="flex items-center gap-1.5 text-[12.5px]">
                    <input
                      type="checkbox"
                      checked={definition.fields.includes(f.key)}
                      onChange={() => toggleField(f.key)}
                      className="h-3.5 w-3.5"
                    />
                    <span className="txt truncate">{f.label}</span>
                  </label>
                ))}
              </div>
            </Field>
          )}

          {grouped && (
            <>
              <Field label="Group by">
                <div className="flex gap-2">
                  <select
                    value={definition.group_by ?? ''}
                    onChange={e =>
                      setDefinition(d => ({
                        ...d,
                        group_by: e.target.value,
                        group_by_interval:
                          byKey.get(e.target.value)?.type === 'DATE' ? d.group_by_interval : null,
                      }))
                    }
                    className="ctl txt flex-1 px-3 py-2 text-[13px]"
                  >
                    {groupableFields.map(f => (
                      <option key={f.key} value={f.key}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                  {definition.group_by && byKey.get(definition.group_by)?.type === 'DATE' && (
                    <select
                      value={definition.group_by_interval ?? ''}
                      onChange={e =>
                        setDefinition(d => ({
                          ...d,
                          group_by_interval: (e.target.value || null) as CustomReportDefinition['group_by_interval'],
                        }))
                      }
                      className="ctl txt px-3 py-2 text-[13px]"
                    >
                      <option value="">Exact date</option>
                      {DATE_INTERVALS.map(i => (
                        <option key={i.value} value={i.value}>
                          By {i.label.toLowerCase()}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </Field>

              <Field label="Summarise with">
                <AggregationEditor
                  aggregations={definition.aggregations}
                  fields={builtinFields}
                  onChange={aggregations => setDefinition(d => ({ ...d, aggregations }))}
                />
              </Field>

              <Field label="Chart">
                <select
                  value={definition.chart_kind ?? ''}
                  onChange={e =>
                    setDefinition(d => ({
                      ...d,
                      chart_kind: (e.target.value || null) as ChartKind | null,
                    }))
                  }
                  className="ctl txt w-full px-3 py-2 text-[13px]"
                >
                  <option value="">Table only</option>
                  <option value="BAR">Bar chart</option>
                  <option value="DONUT">Donut chart</option>
                  <option value="FUNNEL">Funnel</option>
                </select>
              </Field>
            </>
          )}

          <Field label="Filters">
            <FilterEditor
              group={definition.filters ?? { logic: 'AND', conditions: [] }}
              fields={fields}
              onChange={filters => setDefinition(d => ({ ...d, filters }))}
            />
          </Field>

          <Field label="Sort">
            <div className="flex gap-2">
              <select
                value={definition.sort_by ?? ''}
                onChange={e =>
                  setDefinition(d => ({ ...d, sort_by: e.target.value || null }))
                }
                className="ctl txt flex-1 px-3 py-2 text-[13px]"
              >
                <option value="">Default order</option>
                {grouped ? (
                  <>
                    <option value="group">Group</option>
                    {definition.aggregations.map((a, i) => (
                      <option key={i} value={`${a.field ?? 'all'}__${a.op.toLowerCase()}`}>
                        {AGG_LABELS[a.op]} of {a.field ? byKey.get(a.field)?.label ?? a.field : 'all'}
                      </option>
                    ))}
                  </>
                ) : (
                  definition.fields
                    .filter(key => byKey.get(key)?.sortable)
                    .map(key => (
                      <option key={key} value={key}>
                        {byKey.get(key)?.label ?? key}
                      </option>
                    ))
                )}
              </select>
              <select
                value={definition.sort_dir}
                onChange={e =>
                  setDefinition(d => ({ ...d, sort_dir: e.target.value as 'asc' | 'desc' }))
                }
                className="ctl txt px-3 py-2 text-[13px]"
              >
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </div>
          </Field>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!canPreview || previewing}
              onClick={() => void runPreview()}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', previewing && 'animate-spin')} />
              {previewing ? 'Running…' : 'Preview'}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="ctl bd rounded-lg border px-4 py-2 text-[12.5px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!result || busy}
              onClick={() => result && onSave(definition, result)}
              className="ctl bd ml-auto rounded-lg border px-4 py-2 text-[12.5px] font-semibold disabled:opacity-50"
              title={result ? undefined : 'Preview the report before saving'}
            >
              {busy ? 'Saving…' : saveLabel}
            </button>
          </div>

          {previewError && <ListError message={previewError} onRetry={() => void runPreview()} />}

          {result && (
            <div className="space-y-3">
              {result.row_limit_reached && (
                <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3.5 py-2.5 text-[12.5px] text-amber-700 dark:text-amber-400">
                  This report hit its row limit. Narrow the filters to see the whole picture.
                </p>
              )}
              {chartHasData(result) && (
                <div className="surface bd rounded-2xl border p-5">
                  <ReportChart result={result} />
                </div>
              )}
              <div className="surface bd overflow-hidden rounded-2xl border">
                <ReportTable result={result} maxRows={20} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   Aggregations
   ------------------------------------------------------------------ */

function AggregationEditor({
  aggregations,
  fields,
  onChange,
}: {
  aggregations: CustomReportDefinition['aggregations'];
  fields: AvailableFieldInfo[];
  onChange: (aggregations: CustomReportDefinition['aggregations']) => void;
}) {
  const aggregatable = fields.filter(f => f.aggregations.length > 0);

  const add = () => {
    onChange([...aggregations, { field: null, op: 'COUNT' }]);
  };
  const update = (index: number, patch: Partial<{ field: string | null; op: AggOp }>) => {
    onChange(aggregations.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  };
  const remove = (index: number) => {
    onChange(aggregations.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-2">
      {aggregations.map((agg, index) => {
        const field = agg.field ? fields.find(f => f.key === agg.field) : null;
        const allowedOps: AggOp[] = agg.field
          ? (field?.aggregations ?? [])
          : ['COUNT'];
        return (
          <div key={index} className="flex items-center gap-2">
            <select
              value={agg.op}
              onChange={e => update(index, { op: e.target.value as AggOp })}
              className="ctl txt px-2.5 py-1.5 text-[12.5px]"
            >
              {allowedOps.map(op => (
                <option key={op} value={op}>
                  {AGG_LABELS[op]}
                </option>
              ))}
            </select>
            <span className="txt-faint text-[12px]">of</span>
            <select
              value={agg.field ?? ''}
              onChange={e => {
                const key = e.target.value || null;
                const newField = key ? fields.find(f => f.key === key) : null;
                const op = key
                  ? (newField?.aggregations[0] ?? 'COUNT')
                  : 'COUNT';
                update(index, { field: key, op });
              }}
              className="ctl txt flex-1 px-2.5 py-1.5 text-[12.5px]"
            >
              <option value="">All records</option>
              {aggregatable.map(f => (
                <option key={f.key} value={f.key}>
                  {f.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => remove(index)}
              aria-label="Remove"
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
        className="txt-faint hover:txt inline-flex items-center gap-1 text-[11.5px] font-semibold"
      >
        <Plus className="h-3 w-3" /> Add a summary
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------
   Shared bits
   ------------------------------------------------------------------ */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
        {label}
      </span>
      {children}
    </label>
  );
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'rounded-lg px-3.5 py-2 text-[12.5px] font-semibold transition',
        active ? 'text-white' : 'ctl bd border',
      )}
      style={active ? { background: 'var(--accent)' } : undefined}
    >
      {children}
    </button>
  );
}
