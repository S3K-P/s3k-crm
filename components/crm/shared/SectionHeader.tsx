import { cn } from '@/lib/utils';

/* ============================================================
   SECTION HEADER
   Reusable section title bar with optional right-side action.
   Used across dashboard and all CRM module pages.
   ============================================================ */

interface SectionHeaderProps {
  title: string;
  /** Optional right-side element: link, button, badge, etc. */
  action?: React.ReactNode;
  className?: string;
}

export default function SectionHeader({ title, action, className }: SectionHeaderProps) {
  return (
    <div className={cn('mb-3.5 flex items-center justify-between', className)}>
      <h2 className="txt font-display text-[16px] font-bold">{title}</h2>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
