import { AlertTriangle, BadgeCheck, CalendarClock, DollarSign, Flame } from 'lucide-react';
import KpiCard from '@/components/crm/cards/KpiCard';
import { daysFromToday, formatCompactCurrency } from '@/features/ai/shared/format';
import type { NbaRecord } from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA KPI SUMMARY
   Every figure is computed from the same record set the table
   renders, so the totals cannot drift from the data — including
   after local status changes such as "Mark Completed".
   ============================================================ */

const CLOSED_STATUSES: NbaRecord['status'][] = ['Completed', 'Dismissed'];

interface NbaKpiSummaryProps {
  records: NbaRecord[];
}

export default function NbaKpiSummary({ records }: NbaKpiSummaryProps) {
  const open = records.filter(record => !CLOSED_STATUSES.includes(record.status));

  const highPriority = open.filter(
    record => record.priority === 'Critical' || record.priority === 'High',
  ).length;

  const atRisk = open.filter(
    record => record.dealRisk === 'Critical' || record.dealRisk === 'High',
  ).length;

  const dueThisWeek = open.filter(record => daysFromToday(record.nextFollowUp) <= 7).length;

  const expectedRevenue = open.reduce((total, record) => total + record.expectedRevenue, 0);

  const averageConfidence = open.length
    ? Math.round(open.reduce((total, record) => total + record.confidence, 0) / open.length)
    : 0;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      <KpiCard
        label="High Priority"
        value={String(highPriority)}
        delta={`of ${open.length} open recommendations`}
        icon={Flame}
        iconGradient="from-pink-500 to-rose-500"
      />
      <KpiCard
        label="Deals At Risk"
        value={String(atRisk)}
        delta="High or critical deal risk"
        trend={atRisk > 0 ? 'down' : 'flat'}
        icon={AlertTriangle}
        iconGradient="from-amber-500 to-orange-500"
      />
      <KpiCard
        label="Due This Week"
        value={String(dueThisWeek)}
        delta="Follow-ups within 7 days"
        icon={CalendarClock}
        iconGradient="from-violet-600 to-indigo-600"
      />
      <KpiCard
        label="Expected Revenue"
        value={formatCompactCurrency(expectedRevenue)}
        delta="Across open recommendations"
        trend="up"
        icon={DollarSign}
        iconGradient="from-emerald-500 to-green-600"
      />
      <KpiCard
        label="Avg AI Confidence"
        value={`${averageConfidence}%`}
        delta="Weighted equally per record"
        icon={BadgeCheck}
        iconGradient="from-sky-500 to-blue-600"
      />
    </div>
  );
}
