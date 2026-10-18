import { CheckCircle2, ClipboardList, DollarSign, Users } from 'lucide-react';

import KpiCard from '@/components/crm/cards/KpiCard';
import { formatMoney, type DashboardKpis } from '@/features/crm/dashboard';

/* ============================================================
   DASHBOARD KPI STRIP
   The approved mockup's four headline cards. Existing backend
   fields mapped as directly as their meaning allows:
     new_leads               -> "Open Leads"
     pipeline_value          -> "Pipeline Value"
     deals_won_this_month    -> "Deals Won This Month" (new field)
     tasks_due               -> "Tasks Due Today"
   No invented trend deltas — each subtitle states a real fact the
   API already returned, same rule the rest of the dashboard follows.
   The richer Checkpoint-5 KPIs (weighted_pipeline_value, won_revenue,
   lead_conversion_rate) still come back on the same response but are
   not part of this four-card design — the approved mockup only shows
   these four.
   ============================================================ */

interface DashboardKpiStripProps {
  kpis: DashboardKpis;
}

export default function DashboardKpiStrip({ kpis }: DashboardKpiStripProps) {
  return (
    <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
      <KpiCard
        href="/leads"
        label="Open Leads"
        value={String(kpis.new_leads)}
        delta="Last 30 days"
        icon={Users}
        iconGradient="from-emerald-500 to-green-600"
      />
      <KpiCard
        href="/opportunities"
        label="Pipeline Value"
        value={formatMoney(kpis.pipeline_value)}
        delta={kpis.open_opportunities > 0 ? 'Open deals only' : undefined}
        icon={DollarSign}
        iconGradient="from-amber-500 to-orange-500"
      />
      <KpiCard
        href="/opportunities"
        label="Deals Won This Month"
        value={String(kpis.deals_won_this_month)}
        delta={
          kpis.deals_won_this_month > 0
            ? `${formatMoney(kpis.deals_won_this_month_value)} won value`
            : undefined
        }
        trend={kpis.deals_won_this_month > 0 ? 'up' : 'flat'}
        icon={CheckCircle2}
        iconGradient="from-accent to-accent-2"
      />
      <KpiCard
        href="/tasks"
        label="Tasks Due Today"
        value={String(kpis.tasks_due)}
        delta={`${kpis.tasks_due_high_priority} high priority`}
        trend={kpis.tasks_due_high_priority > 0 ? 'down' : 'flat'}
        icon={ClipboardList}
        iconGradient="from-pink-500 to-rose-500"
      />
    </div>
  );
}
