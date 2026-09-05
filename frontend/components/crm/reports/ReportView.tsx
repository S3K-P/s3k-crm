'use client';

import {
  BarChart,
  DonutChart,
  FunnelChart,
} from '@/components/crm/charts/MiniCharts';
import { formatCell, type ReportResult } from '@/features/crm/reports';

/* ============================================================
   REPORT VIEW

   The three ways a report result can be drawn — chart, table,
   single metric — in one place, so the Reports screen and a
   dashboard tile render identically rather than approximately.

   Every one of them works purely from the result envelope's own
   column metadata. A report added to the backend catalogue later
   draws correctly here without a change to this file, which is
   the reason the envelope carries that metadata at all.
   ============================================================ */

/**
 * Whether a chart drawn from this result would say anything.
 *
 * A report with rows but no non-zero value — a rep's view of a pipeline they
 * own none of — draws a row of flat bars that reads as "no data loaded"
 * rather than "the answer is zero". Callers use this to fall back to the
 * table, which states the zeroes plainly.
 *
 * Exported so the chart's own guard and every caller's fallback are the same
 * decision; two copies would drift and leave an empty box behind.
 */
export function chartHasData(result: ReportResult): boolean {
  const { chart } = result;
  if (!chart || result.rows.length === 0) return false;
  return result.rows.some(row => Number(row[chart.value_key] ?? 0) !== 0);
}

/** Charts read the value column; the category is whatever the hint names. */
export function ReportChart({
  result,
  compact = false,
}: {
  result: ReportResult;
  compact?: boolean;
}) {
  const { chart } = result;
  if (!chart || !chartHasData(result)) return null;

  const valueColumn = result.columns.find(column => column.key === chart.value_key);
  const categoryColumn = result.columns.find(column => column.key === chart.category_key);

  // Labels go through the same formatter as the table cells, so a status
  // reads "Proposal sent" in both places rather than only in one.
  const data = result.rows.map(row => ({
    label: formatCell(row[chart.category_key], categoryColumn?.type ?? 'TEXT'),
    value: Number(row[chart.value_key] ?? 0),
  }));

  const format = (value: number) => formatCell(value, valueColumn?.type ?? 'NUMBER');
  const caption = `${result.name}: ${chart.value_key} by ${chart.category_key}`;
  const shown = compact ? data.slice(0, 6) : data;


  return (
    <>
      {chart.kind === 'BAR' && (
        <BarChart data={shown} formatValue={format} caption={caption} />
      )}
      {chart.kind === 'DONUT' && (
        <DonutChart data={shown} formatValue={format} caption={caption} />
      )}
      {chart.kind === 'FUNNEL' && (
        <FunnelChart
          // The funnel draws its bars from `count`; a report that measures a
          // stage in records has no second money figure to put beside it.
          data={shown.map(point => ({ label: point.label, count: point.value }))}
          formatValue={format}
          caption={caption}
        />
      )}
    </>
  );
}

export function ReportTable({
  result,
  maxRows,
}: {
  result: ReportResult;
  maxRows?: number;
}) {
  const rows = maxRows ? result.rows.slice(0, maxRows) : result.rows;
  // Totals describe the whole report, so they are suppressed rather than
  // shown against a truncated table — a footer that does not add up to the
  // rows above it is worse than no footer.
  const truncated = rows.length < result.rows.length;
  const hasTotals = Object.keys(result.totals).length > 0 && !truncated;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead className="bd border-b bg-[var(--surface-2)]">
          <tr>
            {result.columns.map(column => (
              <th
                key={column.key}
                className="txt-faint whitespace-nowrap px-4 py-3 text-[11px] font-bold uppercase tracking-wider"
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {rows.map((row, index) => (
            <tr key={index} className="hover:bg-[var(--surface-2)]">
              {result.columns.map(column => (
                <td key={column.key} className="txt px-4 py-2.5">
                  {formatCell(row[column.key], column.type)}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={result.columns.length}
                className="txt-faint px-4 py-8 text-center"
              >
                Nothing to report for this period.
              </td>
            </tr>
          )}
        </tbody>
        {hasTotals && rows.length > 0 && (
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
      {truncated && (
        <p className="txt-faint px-4 py-2 text-[11.5px]">
          Showing {rows.length} of {result.rows.length} rows.
        </p>
      )}
    </div>
  );
}

/**
 * A single headline number.
 *
 * The first column the report marks summable, or — for a report that totals
 * nothing, such as a funnel — the row count, which is still a true statement
 * about it rather than a zero standing in for "not applicable".
 */
export function ReportMetric({ result }: { result: ReportResult }) {
  const totalKey = Object.keys(result.totals)[0];
  const column = result.columns.find(entry => entry.key === totalKey);

  const value = totalKey
    ? formatCell(result.totals[totalKey], column?.type ?? 'NUMBER')
    : result.rows.length.toLocaleString('en-US');
  const label = totalKey ? (column?.label ?? totalKey) : 'Rows';

  return (
    <div className="flex h-full flex-col items-start justify-center py-4">
      <p className="font-display txt text-[34px] font-extrabold leading-none tracking-tight">
        {value}
      </p>
      <p className="txt-faint mt-1.5 text-[11px] font-bold uppercase tracking-wider">
        {label}
      </p>
    </div>
  );
}
