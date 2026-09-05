'use client';

import { BarChart3, Filter, PieChart, Timer, TrendingUp, Wallet } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import KpiCard from '@/components/crm/cards/KpiCard';
import { BarChart, DonutChart, FunnelChart, LineChart } from '@/components/crm/charts/MiniCharts';
import { formatCompactCurrency } from '@/features/ai/shared/format';
import type { SalesIntelligenceSnapshot as SnapshotData } from '@/features/ai/insights/types';

/* ============================================================
   SALES INTELLIGENCE SNAPSHOT
   Portfolio-level analytics shown beneath the generated
   insights. Figures derive from the same mock dataset the
   Next Best Action page reads, so the two never disagree.
   ============================================================ */

const KPI_ICONS = [Wallet, TrendingUp, Filter, BarChart3];
const KPI_GRADIENTS = [
  'from-violet-600 to-indigo-600',
  'from-emerald-500 to-green-600',
  'from-amber-500 to-orange-500',
  'from-sky-500 to-blue-600',
];

interface SalesIntelligenceSnapshotProps {
  data: SnapshotData;
}

function ChartCard({
  title,
  icon: Icon,
  description,
  children,
}: {
  title: string;
  icon: typeof BarChart3;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="surface bd rounded-2xl border p-4 sm:p-5">
      <div className="mb-4 flex items-start gap-2.5">
        <span className="surface-2 bd grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border" aria-hidden="true">
          <Icon className="h-4 w-4" style={{ color: 'var(--accent)' }} />
        </span>
        <div className="min-w-0">
          <h3 className="txt font-display text-[14.5px] font-bold">{title}</h3>
          <p className="txt-muted text-[12px]">{description}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

export default function SalesIntelligenceSnapshot({ data }: SalesIntelligenceSnapshotProps) {
  return (
    <section aria-labelledby="sales-intelligence-snapshot">
      <SectionHeader
        title="Sales Intelligence Snapshot"
        action={
          <span className="txt-faint text-[12px] font-medium">
            Portfolio view · demonstration data
          </span>
        }
      />
      <h2 id="sales-intelligence-snapshot" className="sr-only">
        Sales Intelligence Snapshot
      </h2>

      {/* ── KPI row ── */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {data.kpis.map((kpi, index) => (
          <KpiCard
            key={kpi.id}
            label={kpi.label}
            value={kpi.value}
            delta={kpi.delta}
            trend={kpi.trend}
            icon={KPI_ICONS[index % KPI_ICONS.length]}
            iconGradient={KPI_GRADIENTS[index % KPI_GRADIENTS.length]}
          />
        ))}
      </div>

      {/* ── Charts ── */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Pipeline by Stage"
          icon={BarChart3}
          description="Open opportunity value across active stages"
        >
          <BarChart
            data={data.pipelineByStage}
            formatValue={formatCompactCurrency}
            caption="Open pipeline value by deal stage"
          />
        </ChartCard>

        <ChartCard
          title="Revenue Forecast"
          icon={TrendingUp}
          description="Closed revenue against forecast, last six months"
        >
          <LineChart
            data={data.revenueForecast}
            formatValue={value => `$${value.toFixed(2)}M`}
            caption="Monthly revenue against forecast over the last six months"
            primaryLabel="Actual"
            compareLabel="Forecast"
          />
        </ChartCard>

        <ChartCard
          title="Lead Conversion Funnel"
          icon={Filter}
          description="Stage-to-stage conversion across the current period"
        >
          <FunnelChart
            data={data.conversionFunnel}
            formatValue={formatCompactCurrency}
            caption="Conversion funnel from leads through to closed won"
          />
        </ChartCard>

        <ChartCard
          title="Opportunity Distribution"
          icon={PieChart}
          description="Open pipeline value by deal size"
        >
          <DonutChart
            data={data.opportunityDistribution}
            formatValue={formatCompactCurrency}
            caption="Share of open pipeline value by deal size band"
          />
        </ChartCard>

        <ChartCard
          title="Deal Velocity"
          icon={Timer}
          description="Average days spent in each stage"
        >
          <BarChart
            data={data.dealVelocityDays}
            formatValue={value => `${value}d`}
            caption="Average number of days opportunities spend in each stage"
            color="#818cf8"
          />
        </ChartCard>
      </div>
    </section>
  );
}
