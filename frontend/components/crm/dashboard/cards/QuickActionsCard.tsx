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
const ACTIONS: { label: string; icon: LucideIcon; href: string }[] = [
  { label: 'Add New Lead', icon: UserPlus, href: '/leads' },
  { label: 'Schedule Meeting', icon: CalendarDays, href: '/meetings' },
  { label: 'Create Opportunity', icon: Target, href: '/opportunities' },
  { label: 'Add Account', icon: Building2, href: '/accounts' },
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
            <span className="surface-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px]">
              <action.icon className="h-4 w-4" style={{ color: 'var(--accent)' }} />
            </span>
            <span className="txt text-[12px] font-semibold leading-tight">{action.label}</span>
          </Link>
        ))}
      </div>
    </DashboardCard>
  );
}
