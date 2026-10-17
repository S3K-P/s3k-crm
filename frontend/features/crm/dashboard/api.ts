/**
 * Dashboard data access.
 *
 * One call, through the shared client in `lib/api-client.ts`, which is the
 * only place the access token and `X-Organization-Id` header are attached.
 * Nothing here knows about tenancy — that is deliberate: a feature module that
 * could choose its own organization would be a second place to get tenant
 * scoping wrong.
 */

import { api } from '@/lib/api-client';
import type {
  DashboardSummary,
  HomeLayout,
  RecentRecordEntry,
} from '@/features/crm/dashboard/types';

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return api.get<DashboardSummary>('/crm/dashboard/summary');
}

export function fetchRecentRecords(): Promise<RecentRecordEntry[]> {
  return api.get<RecentRecordEntry[]>('/crm/dashboard/recent-records');
}

/** The fixed home dashboard's own layout preference — not `/boards/{id}/layout`. */
export function fetchHomeDashboardLayout(): Promise<HomeLayout> {
  return api.get<HomeLayout>('/crm/dashboard/layout');
}

export function saveHomeDashboardLayout(layout: HomeLayout): Promise<HomeLayout> {
  return api.put<HomeLayout>('/crm/dashboard/layout', layout);
}
