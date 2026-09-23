/**
 * Reports — types and API access.
 *
 * Mirrors `backend/app/products/crm/reports/schemas.py`. A report result is
 * self-describing: the columns come back with the rows, so this module needs
 * no per-report types and the screen renders a report added later without a
 * frontend change.
 */

import { humanize } from '@/components/crm/shared/statusVariants';
import { api } from '@/lib/api-client';
import { formatCurrency } from '@/lib/currency';

/** How a value should be formatted. Mirrors the backend `ColumnType`. */
export type ColumnType =
  | 'TEXT'
  | 'STATUS'
  | 'NUMBER'
  | 'CURRENCY'
  | 'PERCENT'
  | 'DATE'
  | 'PERSON';

export type ChartKind = 'BAR' | 'DONUT' | 'FUNNEL';

export interface ReportColumn {
  key: string;
  label: string;
  type: ColumnType;
}

export interface ChartInfo {
  kind: ChartKind;
  category_key: string;
  value_key: string;
}

export interface ReportSummary {
  key: string;
  name: string;
  description: string;
  category: string;
  module: string;
  accepts_date_range: boolean;
  chart: ChartInfo | null;
}

/**
 * A cell. The backend sends JSON scalars only — a `PERSON` column has already
 * been resolved to a display name server-side, so a raw user id never arrives
 * here and the screen never has to resolve one.
 */
export type ReportCell = string | number | null;

export interface ReportResult {
  key: string;
  name: string;
  description: string;
  category: string;
  generated_at: string;
  columns: ReportColumn[];
  rows: Record<string, ReportCell>[];
  totals: Record<string, ReportCell>;
  chart: ChartInfo | null;
  date_from: string | null;
  date_to: string | null;
  row_limit_reached: boolean;
}

export interface ReportRunParams {
  date_from?: string | null;
  date_to?: string | null;
}

export const listReports = () => api.get<ReportSummary[]>('/crm/reports');

export const runReport = (key: string, params: ReportRunParams = {}) =>
  api.post<ReportResult>(`/crm/reports/${key}/run`, params);

/** Group the catalogue for display, preserving the order the API sent. */
export function byCategory(reports: ReportSummary[]): [string, ReportSummary[]][] {
  const groups = new Map<string, ReportSummary[]>();
  for (const report of reports) {
    const bucket = groups.get(report.category);
    if (bucket) bucket.push(report);
    else groups.set(report.category, [report]);
  }
  return [...groups.entries()];
}

/**
 * Render one cell.
 *
 * Currency renders in the CRM's display currency (INR — see lib/currency),
 * the same as every other money figure in the product. Amounts are shown as
 * stored, never converted.
 */
export function formatCell(value: ReportCell, type: ColumnType): string {
  if (value === null || value === undefined) return '—';
  switch (type) {
    case 'STATUS':
      // The one shared helper, so `PROPOSAL_SENT` reads the same in a report
      // as it does on the leads list.
      return humanize(String(value));
    case 'CURRENCY':
      return formatCurrency(Number(value));
    case 'NUMBER':
      return new Intl.NumberFormat('en-US').format(Number(value));
    case 'PERCENT':
      return `${Number(value)}%`;
    case 'DATE':
      return new Date(String(value)).toLocaleDateString();
    default:
      return String(value);
  }
}
