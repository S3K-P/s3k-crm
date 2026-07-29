import { cn } from '@/lib/utils';
import { type LucideIcon } from 'lucide-react';

/* ============================================================
   ACTIVITY ITEM
   Single timeline entry for the Recent Activities feed.
   Reusable in Dashboard, Lead detail, Contact history, etc.
   ============================================================ */

export type ActivityType = 'call' | 'email' | 'meeting' | 'note' | 'deal' | 'lead' | 'task';

export interface ActivityEntry {
  id: string;
  icon: LucideIcon;
  /** Gradient classes for the icon dot */
  iconGradient: string;
  title: string;
  /** e.g. "with John Smith at Acme Corp" */
  detail?: string;
  /** e.g. "2 hours ago" */
  timestamp: string;
}

interface ActivityItemProps {
  activity: ActivityEntry;
  /** Show the vertical line connecting to the next item */
  showConnector?: boolean;
  className?: string;
}

export default function ActivityItem({ activity, showConnector = true, className }: ActivityItemProps) {
  const Icon = activity.icon;

  return (
    <div className={cn('relative flex gap-3', className)}>
      {/* Icon dot + connector line */}
      <div className="flex flex-col items-center">
        <div className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br',
          activity.iconGradient,
        )}>
          <Icon className="h-3.5 w-3.5 text-white" />
        </div>
        {showConnector && (
          <div className="w-px flex-1" style={{ background: 'var(--border)' }} />
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1 pb-4">
        <p className="txt text-[13px] font-semibold leading-tight">{activity.title}</p>
        {activity.detail && (
          <p className="txt-muted mt-0.5 text-[12px]">{activity.detail}</p>
        )}
        <p className="txt-faint mt-1 text-[11px]">{activity.timestamp}</p>
      </div>
    </div>
  );
}
