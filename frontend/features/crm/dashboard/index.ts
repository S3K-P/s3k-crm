// features/crm/dashboard — barrel export
// Dashboard feature module: the organization-scoped summary, its contracts
// and the presenters that shape it for the card components.

export { fetchDashboardSummary } from './api';
export {
  formatMoney,
  formatRelative,
  formatWhen,
  toActivityEntry,
  toMeetingItem,
  toPipelineStages,
  toTaskItem,
} from './presenters';
export { useDashboardSummary } from './useDashboardSummary';
export type { DashboardState, DashboardStatus } from './useDashboardSummary';
export type {
  DashboardActivity,
  DashboardKpis,
  DashboardMeeting,
  DashboardSummary,
  DashboardTask,
  PipelineStageSummary,
} from './types';
