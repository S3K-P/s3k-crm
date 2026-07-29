import { type LucideIcon } from 'lucide-react';
import Link from 'next/link';
import { cn } from '@/lib/utils';

/* ============================================================
   KPI CARD
   Compact metric card for dashboards and summary panels.
   Reusable across Dashboard, Leads, Opportunities, etc.
   ============================================================ */

interface KpiCardProps {
  /** Metric label e.g. "New Leads" */
  label: string;
  /** Primary value e.g. "128" */
  value: string;
  /** Optional delta text e.g. "+12% this week" */
  delta?: string;
  /** Positive (up) or negative (down) trend */
  trend?: 'up' | 'down' | 'flat';
  /** Lucide icon component */
  icon: LucideIcon;
  /** Gradient classes for the icon container */
  iconGradient?: string;
  className?: string;
  /** Optional URL to navigate to when clicked */
  href?: string;
}

export default function KpiCard({
  label,
  value,
  delta,
  trend = 'flat',
  icon: Icon,
  iconGradient = 'from-violet-600 to-indigo-600',
  className,
  href,
}: KpiCardProps) {
  const content = (
    <div className={cn('surface bd rounded-2xl border p-[18px] transition-all hover:-translate-y-0.5 hover:shadow-[0_12px_24px_-12px_rgba(50,30,90,0.15)]', className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="txt-muted text-[12px] font-semibold uppercase tracking-wider">{label}</p>
          <p className="txt font-display mt-1.5 text-[26px] font-extrabold leading-none tracking-tight">
            {value}
          </p>
          {delta && (
            <p className={cn(
              'mt-1.5 text-[11.5px] font-semibold',
              trend === 'up'   && 'text-emerald-600 dark:text-emerald-400',
              trend === 'down' && 'text-red-500 dark:text-red-400',
              trend === 'flat' && 'txt-faint',
            )}>
              {trend === 'up' && '↑ '}
              {trend === 'down' && '↓ '}
              {delta}
            </p>
          )}
        </div>
        <div className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br',
          iconGradient,
        )}>
          <Icon className="h-5 w-5 text-white" />
        </div>
      </div>
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-2xl">
        {content}
      </Link>
    );
  }

  return content;
}
