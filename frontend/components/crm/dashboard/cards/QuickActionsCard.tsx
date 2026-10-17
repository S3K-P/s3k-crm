'use client';

import { Building2, CalendarDays, Target, UserPlus, Zap, type LucideIcon } from 'lucide-react';
import Link from 'next/link';

import DashboardCard from '@/components/crm/dashboard/DashboardCard';

interface QuickActionsCardProps {
  isCustomizing?: boolean;
  onRemove?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLButtonElement>;
}

/** Static navigation, not data — these are links, never metrics. */
const ACTIONS: { label: string; icon: LucideIcon; href: string; gradient: string }[] = [
  { label: 'Add New Lead', icon: UserPlus, href: '/leads', gradient: 'from-emerald-500 to-green-600' },
  { label: 'Schedule Meeting', icon: CalendarDays, href: '/meetings', gradient: 'from-sky-500 to-blue-600' },
  { label: 'Create Opportunity', icon: Target, href: '/opportunities', gradient: 'from-violet-600 to-indigo-600' },
  { label: 'Add Account', icon: Building2, href: '/accounts', gradient: 'from-amber-500 to-orange-500' },
];

export default function QuickActionsCard({ isCustomizing, onRemove, dragHandleProps }: QuickActionsCardProps) {
  return (
    <DashboardCard
      icon={Zap}
      title="Quick Actions"
      isCustomizing={isCustomizing}
      onRemove={onRemove}
      dragHandleProps={dragHandleProps}
    >
      <div className="grid grid-cols-2 gap-2 p-1">
        {ACTIONS.map((action) => (
          <Link
            key={action.label}
            href={action.href}
            className="surface bd flex items-center gap-2.5 rounded-xl border px-3 py-2.5 transition hover:-translate-y-0.5 hover:shadow-[0_12px_24px_-12px_rgba(50,30,90,0.2)]"
          >
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-gradient-to-br ${action.gradient}`}
            >
              <action.icon className="h-4 w-4 text-white" />
            </span>
            <span className="txt text-[12px] font-semibold leading-tight">{action.label}</span>
          </Link>
        ))}
      </div>
    </DashboardCard>
  );
}
