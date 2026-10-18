'use client';

import { useMemo, useState, useSyncExternalStore, type HTMLAttributes } from 'react';
import Link from 'next/link';
import { AlertTriangle, LayoutGrid, RefreshCw, Settings2 } from 'lucide-react';

import DiscoveryBanner from '@/components/crm/dashboard/DiscoveryBanner';
import DashboardKpiStrip from '@/components/crm/dashboard/DashboardKpiStrip';
import DashboardCardGrid from '@/components/crm/dashboard/DashboardCardGrid';
import TodoBar from '@/components/crm/dashboard/TodoBar';
import MyLeadsCard from '@/components/crm/dashboard/cards/MyLeadsCard';
import MyDealsCard from '@/components/crm/dashboard/cards/MyDealsCard';
import MyContactsCard from '@/components/crm/dashboard/cards/MyContactsCard';
import PipelineByStageCard from '@/components/crm/dashboard/cards/PipelineByStageCard';
import TasksFollowUpsCard from '@/components/crm/dashboard/cards/TasksFollowUpsCard';
import RecentRecordsCard from '@/components/crm/dashboard/cards/RecentRecordsCard';
import ActivityTimelineCard from '@/components/crm/dashboard/cards/ActivityTimelineCard';
import UpcomingMeetingsCard from '@/components/crm/dashboard/cards/UpcomingMeetingsCard';
import QuickActionsCard from '@/components/crm/dashboard/cards/QuickActionsCard';
import {
  toPipelineStages,
  useDashboardSummary,
  useHomeDashboardLayout,
  type HomeCardType,
} from '@/features/crm/dashboard';

/* ============================================================
   DASHBOARD PAGE

   The KPI strip, pipeline, tasks and activity feed all come from
   `GET /crm/dashboard/summary`, scoped by the backend to the
   organization the signed-in user is currently acting in. My
   Leads/Deals/Contacts fetch directly from the existing list
   endpoints, filtered to the signed-in user. Recent Records and
   the saved card layout have their own small endpoints.

   This replaces the previous fixed-grid home page. The separate
   user-built "configurable dashboards" feature (saved-report
   boards, at `/dashboards`) is untouched — the link to it just
   moved from the page header's old "Customize dashboard" button
   (which this page's own, different "Customize dashboard" now
   means something else) to the "My Dashboards" link below, so it
   is not orphaned.

   There is no local sample data and no fallback: when a request
   fails, that card (or the page) says so. A dashboard that
   quietly substitutes invented numbers is worse than one that is
   visibly broken.
   ============================================================ */

const subscribeToNothing = () => () => {};
let clientClock: Date | null = null;
const readClientClock = (): Date => (clientClock ??= new Date());
const readServerClock = (): null => null;

function useClientClock(): Date | null {
  return useSyncExternalStore(subscribeToNothing, readClientClock, readServerClock);
}

function greeting(now: Date | null): string {
  if (!now) return 'Welcome back';
  const hour = now.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

function Panel({ children }: { children: React.ReactNode }) {
  return <div className="surface bd flex flex-col items-center gap-3 rounded-2xl border p-12 text-center">{children}</div>;
}

function LoadingDashboard() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading your dashboard…</span>
      <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-[106px] animate-pulse rounded-2xl" style={{ background: 'var(--surface-2)' }} />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-[260px] animate-pulse rounded-2xl" style={{ background: 'var(--surface-2)' }} />
        ))}
      </div>
    </div>
  );
}

function ErrorDashboard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Panel>
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-pink-500 to-rose-500">
        <AlertTriangle className="h-5 w-5 text-white" aria-hidden="true" />
      </div>
      <div>
        <p className="txt text-[14px] font-semibold">Couldn&apos;t load your dashboard</p>
        <p className="txt-muted mx-auto mt-1 max-w-md text-[12.5px]">{message}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="ctl bd mt-1 inline-flex items-center gap-1.5 rounded-xl border px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        Try again
      </button>
    </Panel>
  );
}

export default function DashboardPage() {
  const { status, data, error, reload } = useDashboardSummary();
  const layout = useHomeDashboardLayout();
  const [isCustomizing, setIsCustomizing] = useState(false);

  const now = useClientClock();

  const pipelineStages = useMemo(() => {
    if (!data) return [];
    return toPipelineStages(data.pipeline);
  }, [data]);

  function renderCard(cardType: HomeCardType, dragHandleProps: HTMLAttributes<HTMLButtonElement>) {
    const shared = {
      isCustomizing,
      onRemove: () => layout.setVisible(cardType, false),
      dragHandleProps,
    };

    switch (cardType) {
      case 'MY_LEADS':
        return <MyLeadsCard key={cardType} {...shared} />;
      case 'MY_DEALS':
        return <MyDealsCard key={cardType} {...shared} />;
      case 'MY_CONTACTS':
        return <MyContactsCard key={cardType} {...shared} />;
      case 'PIPELINE_BY_STAGE':
        return (
          <PipelineByStageCard
            key={cardType}
            {...shared}
            status={status}
            stages={pipelineStages}
            total={data?.pipeline_total ?? '0'}
            fetchedAt={now}
          />
        );
      case 'TASKS_FOLLOW_UPS':
        return (
          <TasksFollowUpsCard
            key={cardType}
            {...shared}
            status={status}
            tasks={data?.tasks ?? []}
            fetchedAt={now}
            now={now ?? new Date()}
          />
        );
      case 'RECENT_RECORDS':
        return <RecentRecordsCard key={cardType} {...shared} />;
      case 'ACTIVITY_TIMELINE':
        return (
          <ActivityTimelineCard
            key={cardType}
            {...shared}
            status={status}
            activities={data?.activities ?? []}
            fetchedAt={now}
            now={now ?? new Date()}
          />
        );
      case 'UPCOMING_MEETINGS':
        return (
          <UpcomingMeetingsCard
            key={cardType}
            {...shared}
            status={status}
            meetings={data?.meetings ?? []}
            fetchedAt={now}
            now={now ?? new Date()}
          />
        );
      case 'QUICK_ACTIONS':
        return <QuickActionsCard key={cardType} {...shared} />;
    }
  }

  return (
    <div className="space-y-5 p-6 lg:p-8">
      {/* ── Page Header ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight" style={{ color: 'var(--text)' }}>
            {greeting(now)}
          </h1>
          <p className="txt-muted mt-0.5 text-[13px] font-medium">
            Here&apos;s what&apos;s happening with your sales pipeline today
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
          <Link
            href="/dashboards"
            className="ctl bd flex items-center gap-1.5 rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            My Dashboards
          </Link>
          <button
            type="button"
            onClick={() => setIsCustomizing((v) => !v)}
            className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-[12.5px] font-semibold transition ${isCustomizing ? 'text-white' : ''}`}
            style={
              isCustomizing
                ? { background: 'var(--accent)', borderColor: 'var(--accent)' }
                : { background: 'var(--surface-2)', borderColor: 'var(--border)' }
            }
          >
            <Settings2 className="h-4 w-4" />
            {isCustomizing ? 'Done customizing' : 'Customize dashboard'}
          </button>
        </div>
      </div>

      <DiscoveryBanner />

      {status === 'error' && error !== null && <ErrorDashboard message={error} onRetry={reload} />}
      {status === 'loading' && <LoadingDashboard />}

      {status === 'ready' && data && (
        <>
          <DashboardKpiStrip kpis={data.kpis} />

          {layout.status === 'loading' ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="h-[260px] animate-pulse rounded-2xl" style={{ background: 'var(--surface-2)' }} />
              ))}
            </div>
          ) : (
            <DashboardCardGrid
              visibleCards={layout.visibleCards}
              hiddenCards={layout.hiddenCards}
              isCustomizing={isCustomizing}
              onReorder={layout.reorderVisible}
              onShow={(cardType) => layout.setVisible(cardType, true)}
              renderCard={renderCard}
            />
          )}

          <TodoBar tasks={data.tasks} now={now ?? new Date()} />
        </>
      )}
    </div>
  );
}
