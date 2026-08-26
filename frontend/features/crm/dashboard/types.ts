/**
 * Dashboard contracts, mirroring `app/products/crm/dashboard/schemas.py`.
 *
 * Hand-written for the same reason as `features/auth/types.ts`: doc 11 calls
 * for an `orval`-generated client eventually, and these interfaces are the
 * boundary that generation replaces.
 *
 * Money crosses the wire as a **string**. `deal_value` is a database
 * `NUMERIC`, and parsing it into a JavaScript `number` would quietly round
 * large pipelines; it is formatted, not arithmetic-ed, on this side.
 */

export interface DashboardKpis {
  new_leads: number;
  qualified_leads: number;
  open_opportunities: number;
  pipeline_value: string;
  meetings_today: number;
  tasks_due: number;
  tasks_due_high_priority: number;
  opportunities_closing_soon: number;
}

export interface PipelineStageSummary {
  stage_id: string;
  name: string;
  sort_order: number;
  count: number;
  value: string;
}

export type DashboardTaskPriority = 'HIGH' | 'MEDIUM' | 'LOW';
export type DashboardTaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';

export interface DashboardTask {
  id: string;
  title: string;
  description: string | null;
  priority: DashboardTaskPriority;
  status: DashboardTaskStatus;
  due_date: string | null;
  completed: boolean;
}

export interface DashboardMeeting {
  id: string;
  title: string;
  start_time: string | null;
  end_time: string | null;
  related_label: string | null;
}

export type DashboardActivityType = 'CALL' | 'EMAIL' | 'MEETING' | 'NOTE' | 'TASK';

export interface DashboardActivity {
  id: string;
  type: DashboardActivityType;
  subject: string;
  detail: string | null;
  occurred_at: string;
}

export interface DashboardSummary {
  kpis: DashboardKpis;
  pipeline: PipelineStageSummary[];
  pipeline_total: string;
  /** `null` when open deals span several currencies — see the backend schema. */
  pipeline_currency: string | null;
  tasks: DashboardTask[];
  meetings: DashboardMeeting[];
  activities: DashboardActivity[];
}
