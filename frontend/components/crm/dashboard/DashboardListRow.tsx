import type { ReactNode } from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';

/* ============================================================
   DASHBOARD LIST ROW
   One compact row inside a DashboardCard body: a leading element
   (avatar or checkbox), a title/subtitle pair, and a trailing
   badge or value. Every list card on the dashboard — leads, deals,
   contacts, tasks, recent records — is built from this one shape,
   matching the approved mockup's single `.dcard-row` pattern.
   ============================================================ */

interface DashboardListRowProps {
  leading?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  trailing?: ReactNode;
  href?: string;
  className?: string;
}

export default function DashboardListRow({
  leading,
  title,
  subtitle,
  trailing,
  href,
  className,
}: DashboardListRowProps) {
  const content = (
    <>
      {leading && <div className="shrink-0">{leading}</div>}
      <div className="min-w-0 flex-1">
        <div className="txt truncate text-[12.5px] font-semibold leading-tight">{title}</div>
        {subtitle && (
          <div className="truncate text-[11px]" style={{ color: 'var(--faint)' }}>
            {subtitle}
          </div>
        )}
      </div>
      {trailing && <div className="shrink-0">{trailing}</div>}
    </>
  );

  const rowClassName = cn(
    'flex items-center gap-2.5 rounded-[10px] px-2 py-[7px] transition-colors hover:bg-[var(--surface-2)]',
    className,
  );

  if (href) {
    return (
      <Link href={href} className={cn(rowClassName, 'no-underline')}>
        {content}
      </Link>
    );
  }

  return <div className={rowClassName}>{content}</div>;
}
