/**
 * The custom (ad-hoc) report builder — types and API access (Checkpoint 5).
 *
 * Mirrors `backend/app/products/crm/reports/{fields,conditions,schemas}.py`.
 * A custom report's *result* is the exact same `ReportResult` shape the
 * built-in catalogue returns (see `features/crm/reports`), which is the
 * whole reason `ReportView.tsx`'s `ReportChart`/`ReportTable`/`ReportMetric`
 * need no change at all to render one — they already work from column
 * metadata alone.
 */

import { api } from '@/lib/api-client';

import type { ReportResult } from '.';

export type ReportEntity = 'LEAD' | 'CONTACT' | 'ACCOUNT' | 'OPPORTUNITY' | 'ACTIVITY';

export const REPORT_ENTITIES: { value: ReportEntity; label: string }[] = [
  { value: 'LEAD', label: 'Leads' },
  { value: 'CONTACT', label: 'Contacts' },
  { value: 'ACCOUNT', label: 'Accounts' },
  { value: 'OPPORTUNITY', label: 'Opportunities' },
  { value: 'ACTIVITY', label: 'Activities' },
];

export type AggOp = 'COUNT' | 'SUM' | 'AVG' | 'MIN' | 'MAX';

export const AGG_LABELS: Record<AggOp, string> = {
  COUNT: 'Count',
  SUM: 'Sum',
  AVG: 'Average',
  MIN: 'Minimum',
  MAX: 'Maximum',
};

export type DateInterval = 'day' | 'week' | 'month' | 'quarter' | 'year';

export const DATE_INTERVALS: { value: DateInterval; label: string }[] = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
];

export interface AvailableFieldInfo {
  key: string;
  label: string;
  type: 'TEXT' | 'STATUS' | 'NUMBER' | 'CURRENCY' | 'PERCENT' | 'DATE' | 'PERSON';
  is_custom: boolean;
  filterable: boolean;
  groupable: boolean;
  sortable: boolean;
  aggregations: AggOp[];
}

export type ReportFilterOperator =
  | 'eq'
  | 'ne'
  | 'contains'
  | 'starts_with'
  | 'ends_with'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'between'
  | 'in'
  | 'is_empty'
  | 'is_not_empty';

/** Operators offered per column type — mirrors `reports.conditions.ALLOWED_OPERATORS`. */
export const OPERATORS_BY_TYPE: Record<AvailableFieldInfo['type'], ReportFilterOperator[]> = {
  TEXT: ['eq', 'ne', 'contains', 'starts_with', 'ends_with', 'in', 'is_empty', 'is_not_empty'],
  STATUS: ['eq', 'ne', 'in', 'is_empty', 'is_not_empty'],
  PERSON: ['eq', 'ne', 'in', 'is_empty', 'is_not_empty'],
  NUMBER: ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'in', 'is_empty', 'is_not_empty'],
  CURRENCY: ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'in', 'is_empty', 'is_not_empty'],
  PERCENT: ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'in', 'is_empty', 'is_not_empty'],
  DATE: ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'is_empty', 'is_not_empty'],
};

export const OPERATOR_LABELS: Record<ReportFilterOperator, string> = {
  eq: 'is',
  ne: 'is not',
  contains: 'contains',
  starts_with: 'starts with',
  ends_with: 'ends with',
  gt: 'is greater than',
  gte: 'is at least',
  lt: 'is less than',
  lte: 'is at most',
  between: 'is between',
  in: 'is one of',
  is_empty: 'is empty',
  is_not_empty: 'is not empty',
};

/** A field's value may also be a relative period, for a DATE column. */
export const RELATIVE_PERIODS: { value: string; label: string }[] = [
  { value: 'TODAY', label: 'Today' },
  { value: 'LAST_7_DAYS', label: 'Last 7 days' },
  { value: 'LAST_30_DAYS', label: 'Last 30 days' },
  { value: 'LAST_90_DAYS', label: 'Last 90 days' },
  { value: 'THIS_MONTH', label: 'This month' },
  { value: 'LAST_MONTH', label: 'Last month' },
  { value: 'THIS_QUARTER', label: 'This quarter' },
  { value: 'LAST_QUARTER', label: 'Last quarter' },
  { value: 'THIS_YEAR', label: 'This year' },
];

export interface ReportCondition {
  field: string;
  operator: ReportFilterOperator;
  value?: unknown;
}

export interface ReportFilterGroup {
  logic: 'AND' | 'OR';
  conditions: ReportCondition[];
}

export interface ReportAggregation {
  field?: string | null;
  op: AggOp;
}

export type ChartKind = 'BAR' | 'DONUT' | 'FUNNEL';

export interface CustomReportDefinition {
  entity: ReportEntity;
  fields: string[];
  filters?: ReportFilterGroup | null;
  group_by?: string | null;
  group_by_interval?: DateInterval | null;
  aggregations: ReportAggregation[];
  sort_by?: string | null;
  sort_dir: 'asc' | 'desc';
  date_field?: string | null;
  chart_kind?: ChartKind | null;
}

export const EMPTY_CUSTOM_DEFINITION: CustomReportDefinition = {
  entity: 'LEAD',
  fields: [],
  filters: { logic: 'AND', conditions: [] },
  group_by: null,
  group_by_interval: null,
  aggregations: [],
  sort_by: null,
  sort_dir: 'asc',
  date_field: null,
  chart_kind: null,
};

export const listCustomFields = (entity: ReportEntity) =>
  api.get<AvailableFieldInfo[]>(`/crm/reports/custom/fields?entity=${entity}`);

export const previewCustomReport = (
  definition: CustomReportDefinition,
  params: { date_from?: string | null; date_to?: string | null } = {},
) =>
  api.post<ReportResult>('/crm/reports/custom/preview', {
    definition,
    ...params,
  });
