import { AlertTriangle, Flame, ListChecks, UserRoundX, type LucideIcon } from 'lucide-react';

import KpiCard from '@/components/crm/cards/KpiCard';
import { cn } from '@/lib/utils';

/* ============================================================
   NBA KPI STRIP

   Four counts, each read straight off data the page already
   holds — the ranked queue and the AI Insights digest — and each
   a shortcut to the filter that shows exactly those records.
   A count whose source failed to load shows "—", never zero.
   ============================================================ */

export interface NbaKpis {
  queued: number;
  deals: number;
  leads: number;
  high: number;
  /** From the AI Insights digest, which loads separately and may fail on its own. */
  atRisk: number | 'loading' | 'unavailable';
  leadsWithoutFollowUp: number;
}

export type NbaKpiShortcut = 'ALL' | 'HIGH' | 'AT_RISK' | 'LEADS_NO_FOLLOW_UP';

function Tile({
  active,
  onClick,
  label,
  value,
  delta,
  icon,
  gradient,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  value: string;
  delta: string;
  icon: LucideIcon;
  gradient: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className="rounded-2xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-default"
    >
      <KpiCard
        label={label}
        value={value}
        delta={delta}
        icon={icon}
        iconGradient={gradient}
        className={cn('h-full', active && 'border-[var(--accent)] ring-1 ring-[var(--accent)]')}
      />
    </button>
  );
}

export default function NbaKpiStrip({
  kpis,
  active,
  onShortcut,
}: {
  kpis: NbaKpis;
  active: NbaKpiShortcut | null;
  onShortcut: (shortcut: NbaKpiShortcut) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile
        active={active === 'ALL'}
        onClick={() => onShortcut('ALL')}
        label="Actions needed"
        value={String(kpis.queued)}
        delta={`${kpis.deals} ${kpis.deals === 1 ? 'deal' : 'deals'} · ${kpis.leads} ${kpis.leads === 1 ? 'lead' : 'leads'}`}
        icon={ListChecks}
        gradient="from-violet-600 to-indigo-600"
      />
      <Tile
        active={active === 'HIGH'}
        onClick={() => onShortcut('HIGH')}
        label="High priority"
        value={String(kpis.high)}
        delta="Ranked High on CRM signals"
        icon={Flame}
        gradient="from-pink-500 to-rose-500"
      />
      <Tile
        active={active === 'AT_RISK'}
        onClick={() => onShortcut('AT_RISK')}
        disabled={typeof kpis.atRisk !== 'number'}
        label="Deals at risk"
        value={typeof kpis.atRisk === 'number' ? String(kpis.atRisk) : '—'}
        delta={
          kpis.atRisk === 'loading'
            ? 'Checking…'
            : kpis.atRisk === 'unavailable'
              ? 'AI Insights digest unavailable'
              : 'Flagged by AI Insights'
        }
        icon={AlertTriangle}
        gradient="from-amber-500 to-orange-500"
      />
      <Tile
        active={active === 'LEADS_NO_FOLLOW_UP'}
        onClick={() => onShortcut('LEADS_NO_FOLLOW_UP')}
        label="Leads to follow up"
        value={String(kpis.leadsWithoutFollowUp)}
        delta="No open task scheduled"
        icon={UserRoundX}
        gradient="from-sky-500 to-blue-600"
      />
    </div>
  );
}
