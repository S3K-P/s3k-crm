// features/crm/dashboard — barrel export
// Dashboard feature module: the organization-scoped summary, its contracts
// and the presenters that shape it for the card components.

export {
  fetchDashboardSummary,
  fetchHomeDashboardLayout,
  fetchRecentRecords,
  saveHomeDashboardLayout,
} from './api';
export { formatMoney, formatRelative, formatWhen, toActivityEntry, toPipelineStages } from './presenters';
export type { PipelineStage } from './presenters';
export { useDashboardSummary } from './useDashboardSummary';
export type { DashboardState, DashboardStatus } from './useDashboardSummary';
export { useHomeDashboardLayout } from './useHomeDashboardLayout';
export type { UseHomeDashboardLayout, HomeDashboardLayoutStatus } from './useHomeDashboardLayout';
export { useOwnedCardList } from './useOwnedCardList';
export type { OwnedCardListState } from './useOwnedCardList';
export { useRecentRecords } from './useRecentRecords';
export type { RecentRecordsState } from './useRecentRecords';
export type {
  DashboardActivity,
  DashboardKpis,
  DashboardMeeting,
  DashboardSummary,
  DashboardTask,
  HomeCardConfig,
  HomeCardType,
  HomeLayout,
  LeadSourcePerformance,
  OwnerPipelineSummary,
  PipelineStageSummary,
  RecentRecordEntry,
  RecentRecordType,
  RevenueMonth,
} from './types';
