import type { ReactNode } from 'react';
import { AlertTriangle, type LucideIcon } from 'lucide-react';

/* ============================================================
   DASHBOARD CARD BODY
   The loading / error / empty / populated switch every dashboard
   list card needs, in one place. Mirrors the idiom the previous
   page.tsx used (EmptyNote / Skeleton / LoadingDashboard) — the
   mockup's Populated/Empty/Loading pill switcher was a design-
   review artifact only; this is the real per-card equivalent,
   driven by each card's own request state rather than a toggle.
   ============================================================ */

function RowSkeleton() {
  return (
    <div className="flex items-center gap-2.5 px-2 py-[7px]">
      <div
        className="h-7 w-7 shrink-0 animate-pulse rounded-full"
        style={{ background: 'var(--surface-2)' }}
      />
      <div className="flex-1 space-y-1.5">
        <div
          className="h-[10px] w-3/5 animate-pulse rounded"
          style={{ background: 'var(--surface-2)' }}
        />
        <div
          className="h-[8px] w-2/5 animate-pulse rounded"
          style={{ background: 'var(--surface-2)' }}
        />
      </div>
    </div>
  );
}

interface DashboardCardBodyProps<T> {
  status: 'loading' | 'ready' | 'error';
  items: T[];
  error?: string | null;
  emptyIcon: LucideIcon;
  emptyTitle: string;
  emptyDescription: string;
  renderRow: (item: T) => ReactNode;
  skeletonRows?: number;
}

export default function DashboardCardBody<T>({
  status,
  items,
  error,
  emptyIcon: EmptyIcon,
  emptyTitle,
  emptyDescription,
  renderRow,
  skeletonRows = 2,
}: DashboardCardBodyProps<T>) {
  if (status === 'loading') {
    return (
      <div aria-busy="true" aria-live="polite">
        <span className="sr-only">Loading…</span>
        {Array.from({ length: skeletonRows }, (_, i) => <RowSkeleton key={i} />)}
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex flex-col items-center gap-1.5 px-4 py-6 text-center">
        <AlertTriangle className="h-5 w-5 text-red-500 dark:text-red-400" />
        <p className="txt-muted text-[12px]">{error ?? 'Could not load this list.'}</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-1.5 px-4 py-6 text-center">
        <EmptyIcon className="h-9 w-9" style={{ color: 'var(--faint)' }} />
        <h4 className="txt text-[13px] font-bold">{emptyTitle}</h4>
        <p className="txt-muted text-[12px] leading-snug">{emptyDescription}</p>
      </div>
    );
  }

  return <div>{items.map(renderRow)}</div>;
}
