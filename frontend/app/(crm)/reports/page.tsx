'use client';

import { useCallback, useEffect, useState } from 'react';
import { BarChart3, CalendarRange, RefreshCw } from 'lucide-react';

import { cn } from '@/lib/utils';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import { ListEmpty, ListError } from '@/components/crm/shared/ListStates';
import { BarChart, DonutChart, FunnelChart } from '@/components/crm/charts/MiniCharts';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  byCategory,
  formatCell,
  listReports,
  runReport,
  type ReportResult,
  type ReportSummary,
} from '@/features/crm/reports';

/* ============================================================
   REPORTS

   The catalogue on the left, the selected report on the right.

   The screen knows nothing about any individual report: a result
   describes its own columns, so a report added to the backend
   catalogue appears here — table, chart and totals — with no
   change to this file. That is the whole reason the result
   envelope carries its column metadata.
   ============================================================ */

/** Charts read the value column; a category is whatever the hint names. */
function ReportChart({ result }: { result: ReportResult }) {
  const { chart } = result;
  if (!chart || result.rows.length === 0) return null;

  const valueColumn = result.columns.find(column => column.key === chart.value_key);
  const categoryColumn = result.columns.find(column => column.key === chart.category_key);

  // Labels go through the same formatter as the table cells, so a status
  // reads "Proposal sent" in both places rather than only in one.
  const data = result.rows.map(row => ({
    label: formatCell(row[chart.category_key], categoryColumn?.type ?? 'TEXT'),
    value: Number(row[chart.value_key] ?? 0),
  }));

  // A chart of nothing but zeroes is a flat bar with no information in it;
  // the table underneath already says the same thing more honestly.
  if (data.every(point => point.value === 0)) return null;

  const format = (value: number) =>
    formatCell(value, valueColumn?.type ?? 'NUMBER');
  const caption = `${result.name}: ${chart.value_key} by ${chart.category_key}`;

  return (
    <div className="surface bd rounded-2xl border p-5">
      {chart.kind === 'BAR' && (
        <BarChart data={data} formatValue={format} caption={caption} />
      )}
      {chart.kind === 'DONUT' && (
        <DonutChart data={data} formatValue={format} caption={caption} />
      )}
      {chart.kind === 'FUNNEL' && (
        <FunnelChart
          // The funnel draws its bars from `count`; a report that measures a
          // stage in records has no second money figure to put beside it.
          data={data.map(point => ({ label: point.label, count: point.value }))}
          formatValue={format}
          caption={caption}
        />
      )}
    </div>
  );
}

function ReportTable({ result }: { result: ReportResult }) {
  const hasTotals = Object.keys(result.totals).length > 0;

  return (
    <div className="surface bd overflow-hidden rounded-2xl border">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[13px]">
          <thead className="bd border-b bg-[var(--surface-2)]">
            <tr>
              {result.columns.map(column => (
                <th
                  key={column.key}
                  className="txt-faint px-4 py-3 text-[11px] font-bold uppercase tracking-wider"
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            {result.rows.map((row, index) => (
              <tr key={index} className="hover:bg-[var(--surface-2)]">
                {result.columns.map(column => (
                  <td key={column.key} className="txt px-4 py-2.5">
                    {formatCell(row[column.key], column.type)}
                  </td>
                ))}
              </tr>
            ))}
            {result.rows.length === 0 && (
              <tr>
                <td colSpan={result.columns.length} className="txt-faint px-4 py-8 text-center">
                  Nothing to report for this period.
                </td>
              </tr>
            )}
          </tbody>
          {hasTotals && result.rows.length > 0 && (
            <tfoot className="bd border-t bg-[var(--surface-2)]">
              <tr>
                {result.columns.map((column, index) => (
                  <td key={column.key} className="txt px-4 py-2.5 font-bold">
                    {index === 0
                      ? 'Total'
                      : column.key in result.totals
                        ? formatCell(result.totals[column.key], column.type)
                        : ''}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const [catalogue, setCatalogue] = useState<ReportSummary[] | null>(null);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [reload, setReload] = useState(0);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const active = catalogue?.find(report => report.key === selected) ?? null;

  const execute = useCallback(async (key: string, from: string, to: string) => {
    setRunning(true);
    try {
      setResult(await runReport(key, { date_from: from || null, date_to: to || null }));
      setRunError(null);
    } catch (cause) {
      setResult(null);
      setRunError(describeApiError(cause, 'Unable to run this report right now.'));
    } finally {
      setRunning(false);
    }
  }, []);

  // Load the catalogue, then run whichever report comes first so the screen
  // opens with something on it rather than an instruction to pick.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const reports = await listReports();
        if (cancelled) return;
        setCatalogue(reports);
        setCatalogueError(null);
        if (reports.length > 0) {
          setSelected(reports[0].key);
          await execute(reports[0].key, '', '');
        }
      } catch (cause) {
        if (!cancelled) setCatalogueError(describeApiError(cause, 'Unable to load reports.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [execute, reload]);

  const choose = (key: string) => {
    setSelected(key);
    setDateFrom('');
    setDateTo('');
    void execute(key, '', '');
  };

  return (
    <div className="flex h-full flex-col space-y-5 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
          <BarChart3 className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold leading-tight tracking-tight">
            Reports
          </h1>
          <p className="txt-muted mt-0.5 text-[13px] font-medium">
            Every report counts only the records you can open.
          </p>
        </div>
      </div>

      {catalogueError && (
        <ListError message={catalogueError} onRetry={() => setReload(count => count + 1)} />
      )}

      {catalogue?.length === 0 && (
        <ListEmpty
          title="No reports available"
          hint="Reports follow the records you can see. Ask an administrator for access to leads, deals or accounts."
        />
      )}

      <div className="grid flex-1 gap-6 lg:grid-cols-[260px_1fr]">
        {/* Catalogue */}
        <nav className="space-y-5" aria-label="Reports">
          {catalogue &&
            byCategory(catalogue).map(([category, reports]) => (
              <div key={category}>
                <p className="txt-faint mb-2 text-[10.5px] font-bold uppercase tracking-wider">
                  {category}
                </p>
                <div className="space-y-1">
                  {reports.map(report => (
                    <button
                      key={report.key}
                      type="button"
                      onClick={() => choose(report.key)}
                      aria-current={report.key === selected ? 'true' : undefined}
                      className={cn(
                        'w-full rounded-lg px-3 py-2 text-left text-[12.5px] font-medium transition-colors',
                        report.key === selected
                          ? 'bg-[var(--accent-soft)] text-[var(--accent)]'
                          : 'txt-muted hover:surface-2',
                      )}
                    >
                      {report.name}
                    </button>
                  ))}
                </div>
              </div>
            ))}
        </nav>

        {/* Selected report */}
        <div className="min-w-0 space-y-5">
          {active && (
            <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <SectionHeader title={active.name} />
                <p className="txt-muted text-[12.5px]">{active.description}</p>
              </div>

              <div className="flex flex-wrap items-end gap-2">
                {active.accepts_date_range && (
                  <>
                    <label className="txt-faint flex flex-col gap-1 text-[10.5px] font-bold uppercase tracking-wider">
                      <span className="flex items-center gap-1">
                        <CalendarRange className="h-3 w-3" /> From
                      </span>
                      <input
                        type="date"
                        value={dateFrom}
                        onChange={event => setDateFrom(event.target.value)}
                        className="ctl txt px-2.5 py-1.5 text-[12.5px] font-normal normal-case tracking-normal"
                      />
                    </label>
                    <label className="txt-faint flex flex-col gap-1 text-[10.5px] font-bold uppercase tracking-wider">
                      To
                      <input
                        type="date"
                        value={dateTo}
                        onChange={event => setDateTo(event.target.value)}
                        className="ctl txt px-2.5 py-1.5 text-[12.5px] font-normal normal-case tracking-normal"
                      />
                    </label>
                  </>
                )}
                <button
                  type="button"
                  disabled={running}
                  onClick={() => void execute(active.key, dateFrom, dateTo)}
                  className="flex items-center gap-2 rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
                  style={{ background: 'var(--accent)' }}
                >
                  <RefreshCw className={cn('h-3.5 w-3.5', running && 'animate-spin')} />
                  {running ? 'Running…' : 'Run'}
                </button>
              </div>
            </div>
          )}

          {runError && active && (
            <ListError
              message={runError}
              onRetry={() => void execute(active.key, dateFrom, dateTo)}
            />
          )}

          {result && (
            <>
              {result.row_limit_reached && (
                <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3.5 py-2.5 text-[12.5px] text-amber-700 dark:text-amber-400">
                  This report hit its row limit. Narrow the period to see the whole picture.
                </p>
              )}
              <ReportChart result={result} />
              <ReportTable result={result} />
              <p className="txt-faint text-[11.5px]">
                Generated {new Date(result.generated_at).toLocaleString()}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
