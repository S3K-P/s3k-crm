/**
 * Configurable dashboards — types and API access.
 *
 * Mirrors `backend/app/products/crm/dashboard/{models,schemas}.py`. Separate
 * from `features/crm/dashboard` (singular), which backs the fixed home screen;
 * these are the boards a user builds out of saved reports.
 */

import { api } from '@/lib/api-client';
import type { Page } from '@/features/shared/types/api';

import type { ReportResult } from '@/features/crm/reports';
import type { ShareScope } from '@/features/crm/reports/library';

/** Mirrors the backend `ComponentDisplay`. */
export type ComponentDisplay = 'CHART' | 'TABLE' | 'METRIC';

/**
 * The grid a tile's width is measured in. Twelve columns, so halves, thirds
 * and quarters are all whole numbers. Mirrors `DASHBOARD_GRID_COLUMNS`.
 */
export const GRID_COLUMNS = 12;

/** Widths offered in the UI. Arbitrary widths are legal; these are the useful ones. */
export const WIDTH_CHOICES: { value: number; label: string }[] = [
  { value: 4, label: 'One third' },
  { value: 6, label: 'Half' },
  { value: 8, label: 'Two thirds' },
  { value: 12, label: 'Full width' },
];

export interface Dashboard {
  id: string;
  name: string;
  description: string | null;
  owner_id: string | null;
  visibility: ShareScope;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface DashboardComponent {
  id: string;
  dashboard_id: string;
  saved_report_id: string;
  title: string | null;
  display: ComponentDisplay;
  sort_order: number;
  width: number;
}

export interface DashboardDetail extends Dashboard {
  components: DashboardComponent[];
}

/**
 * One rendered tile. Exactly one of `result` and `unavailable` is set — the
 * backend guarantees it, and the UI branches on `result` being null rather
 * than trying to interpret both.
 */
export interface DashboardComponentData {
  id: string;
  saved_report_id: string;
  title: string;
  display: ComponentDisplay;
  sort_order: number;
  width: number;
  result: ReportResult | null;
  unavailable: string | null;
}

export interface DashboardData {
  id: string;
  name: string;
  description: string | null;
  generated_at: string;
  components: DashboardComponentData[];
}

/** Why a tile could not be drawn, in words. Mirrors the backend's codes. */
export function unavailableMessage(code: string): string {
  switch (code) {
    case 'permission':
      return 'You do not have access to the records behind this report.';
    case 'report_unavailable':
      return 'The report behind this tile is no longer available.';
    default:
      return 'This tile could not be loaded.';
  }
}

export const listDashboards = () =>
  api.get<Page<Dashboard>>('/crm/dashboard/boards?page_size=200&sort_by=name&sort_dir=asc');

export const createDashboard = (input: {
  name: string;
  description?: string | null;
  visibility?: ShareScope;
  is_default?: boolean;
}) => api.post<Dashboard>('/crm/dashboard/boards', input);

export const getDashboard = (id: string) =>
  api.get<DashboardDetail>(`/crm/dashboard/boards/${id}`);

export const updateDashboard = (
  id: string,
  input: { name?: string; description?: string | null; visibility?: ShareScope; is_default?: boolean },
) => api.patch<Dashboard>(`/crm/dashboard/boards/${id}`, input);

export const deleteDashboard = (id: string) =>
  api.delete<void>(`/crm/dashboard/boards/${id}`);

export const renderDashboard = (id: string) =>
  api.get<DashboardData>(`/crm/dashboard/boards/${id}/data`);

export const addComponent = (
  dashboardId: string,
  input: {
    saved_report_id: string;
    title?: string | null;
    display?: ComponentDisplay;
    width?: number;
  },
) => api.post<DashboardComponent>(`/crm/dashboard/boards/${dashboardId}/components`, input);

export const updateComponent = (
  dashboardId: string,
  componentId: string,
  input: { title?: string | null; display?: ComponentDisplay; width?: number },
) =>
  api.patch<DashboardComponent>(
    `/crm/dashboard/boards/${dashboardId}/components/${componentId}`,
    input,
  );

export const removeComponent = (dashboardId: string, componentId: string) =>
  api.delete<void>(`/crm/dashboard/boards/${dashboardId}/components/${componentId}`);

export const reorderComponents = (dashboardId: string, order: string[]) =>
  api.put<DashboardComponent[]>(`/crm/dashboard/boards/${dashboardId}/layout`, { order });
