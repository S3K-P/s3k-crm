'use client';

import { useMemo, useSyncExternalStore } from 'react';
import Link from 'next/link';
import {
  UserPlus, CalendarDays, Target, Building2,
  Users, CheckCircle2, DollarSign, ClipboardList,
  ArrowRight, AlertTriangle, RefreshCw,
} from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import KpiCard from '@/components/crm/cards/KpiCard';
import TaskCard from '@/components/crm/cards/TaskCard';
import MeetingCard from '@/components/crm/cards/MeetingCard';
import PipelineStageCard from '@/components/crm/cards/PipelineStageCard';
import ActivityItem from '@/components/crm/cards/ActivityItem';
import QuickActionButton from '@/components/crm/cards/QuickActionButton';
import {
  formatMoney,
  toActivityEntry,
  toMeetingItem,
  toPipelineStages,
  toTaskItem,
  useDashboardSummary,
} from '@/features/crm/dashboard';

/* ============================================================
   DASHBOARD PAGE

   Every figure on this page comes from
   `GET /api/v1/crm/dashboard/summary`, scoped by the backend to
   the organization the signed-in user is currently acting in.

   There is no local sample data and no fallback: when the API
   cannot be reached the page says so. A dashboard that quietly
   substitutes invented numbers is worse than one that is
   visibly broken.
   ============================================================ */

/** Static navigation, not data — these are links, not metrics. */
const QUICK_ACTIONS = [
  { label: 'Add New Lead',        icon: UserPlus,     href: '/leads',         gradient: 'from-emerald-500 to-green-600' },
  { label: 'Schedule Meeting',    icon: CalendarDays, href: '/meetings',      gradient: 'from-sky-500 to-blue-600' },
  { label: 'Create Opportunity',  icon: Target,       href: '/opportunities', gradient: 'from-violet-600 to-indigo-600' },
  { label: 'Add Account',         icon: Building2,    href: '/accounts',      gradient: 'from-amber-500 to-orange-500' },
];

/* ============================================================
   THE VIEWER'S CLOCK

   The greeting and the date line depend on the reader's local
   time, which the server does not share — rendering them during
   SSR guarantees a hydration mismatch across a time-zone
   boundary. `useSyncExternalStore` is the sanctioned way to say
   "this value does not exist on the server": it yields `null`
   there and a stable client time after hydration.
   ============================================================ */

const subscribeToNothing = () => () => {};

let clientClock: Date | null = null;
const readClientClock = (): Date => (clientClock ??= new Date());
const readServerClock = (): null => null;

function useClientClock(): Date | null {
  return useSyncExternalStore(subscribeToNothing, readClientClock, readServerClock);
}

/* ============================================================
   SHARED BITS
   ============================================================ */

function Panel({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={`surface bd rounded-2xl border p-[18px] ${className ?? ''}`}>{children}</div>;
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="txt-faint px-1 py-6 text-center text-[12.5px] font-medium">{children}</p>
  );
}

function Skeleton({ className }: { className: string }) {
  return (
    <div
      className={`motion-safe:animate-pulse rounded-xl ${className}`}
      style={{ background: 'var(--surface-2)' }}
    />
  );
}

/* ============================================================
   NON-DATA STATES
   ============================================================ */

function LoadingDashboard() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading your dashboard…</span>
      <div className="grid grid-cols-2 gap-3.5 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-[106px]" />)}
      </div>
      <div className="grid gap-[18px] lg:grid-cols-2">
        <Skeleton className="h-[320px]" />
        <Skeleton className="h-[320px]" />
      </div>
      <div className="grid gap-[18px] lg:grid-cols-[1.5fr_1fr]">
        <Skeleton className="h-[300px]" />
        <Skeleton className="h-[300px]" />
      </div>
    </div>
  );
}

function ErrorDashboard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Panel className="flex flex-col items-center gap-3 py-12 text-center">
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

/* ============================================================
   PAGE
   ============================================================ */

export default function DashboardPage() {
  const { status, data, error, reload } = useDashboardSummary();

  const now = useClientClock();

  const view = useMemo(() => {
    // `data` only ever arrives client-side, so this — and the clock it reads —
    // never runs during SSR.
    if (!data) return null;
    const now = new Date();
    return {
      tasks: data.tasks.map((task) => toTaskItem(task, now)),
      meetings: data.meetings.map((meeting) => toMeetingItem(meeting, now)),
      pipeline: toPipelineStages(data.pipeline, data.pipeline_currency),
      activities: data.activities.map((activity) => toActivityEntry(activity, now)),
    };
  }, [data]);

  const kpis = data?.kpis;

  return (
    <div className="space-y-6 p-6 lg:p-8">

      {/* ── Page Header ── */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1
            className="font-display text-[22px] font-extrabold leading-tight tracking-tight"
            style={{ color: 'var(--text)' }}
          >
            {greeting(now)} 👋
          </h1>
          <p className="txt-muted mt-0.5 text-[13px] font-medium">
            Here&apos;s what&apos;s happening with your sales pipeline today
          </p>
        </div>
        <p className="txt-faint text-[12.5px] font-medium">
          {now?.toLocaleDateString('en-US', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
          }) ?? ''}
        </p>
      </div>

      {status === 'error' && error !== null && (
        <ErrorDashboard message={error} onRetry={reload} />
      )}
      {(status === 'loading' || (status === 'ready' && view === null)) && <LoadingDashboard />}

      {status === 'ready' && view !== null && kpis && data && (
        <>
          {/* ── KPI Cards ── */}
          <div className="grid grid-cols-2 gap-3.5 md:grid-cols-3 xl:grid-cols-6">
            <KpiCard
              href="/leads" label="New Leads" value={String(kpis.new_leads)}
              delta="Last 30 days" icon={Users} iconGradient="from-emerald-500 to-green-600"
            />
            <KpiCard
              href="/qualification" label="Qualified" value={String(kpis.qualified_leads)}
              icon={CheckCircle2} iconGradient="from-violet-600 to-indigo-600"
            />
            <KpiCard
              href="/opportunities" label="Open Opps" value={String(kpis.open_opportunities)}
              delta={`${kpis.opportunities_closing_soon} closing soon`}
              icon={Target} iconGradient="from-sky-500 to-blue-600"
            />
            <KpiCard
              href="/opportunities" label="Pipeline Value"
              value={formatMoney(kpis.pipeline_value, data.pipeline_currency)}
              delta={data.pipeline_currency ? 'Open deals only' : 'Mixed currencies'}
              icon={DollarSign} iconGradient="from-amber-500 to-orange-500"
            />
            <KpiCard
              href="/meetings" label="Meetings Today" value={String(kpis.meetings_today)}
              icon={CalendarDays} iconGradient="from-pink-500 to-rose-500"
            />
            <KpiCard
              label="Tasks Due" value={String(kpis.tasks_due)}
              delta={`${kpis.tasks_due_high_priority} high priority`}
              icon={ClipboardList} iconGradient="from-violet-500 to-purple-600"
            />
          </div>

          {/* ── Middle Row: Tasks + Meetings ── */}
          <div className="grid gap-[18px] lg:grid-cols-2">
            <Panel>
              <SectionHeader
                title="Open Tasks"
                action={
                  <Link href="/leads" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                    View all →
                  </Link>
                }
              />
              <div className="space-y-2">
                {view.tasks.length === 0
                  ? <EmptyNote>Nothing open. Tasks you create will appear here.</EmptyNote>
                  : view.tasks.map((task) => <TaskCard key={task.id} task={task} />)}
              </div>
            </Panel>

            <Panel>
              <SectionHeader
                title="Upcoming Meetings"
                action={
                  <Link href="/meetings" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                    View all →
                  </Link>
                }
              />
              <div className="space-y-2">
                {view.meetings.length === 0
                  ? <EmptyNote>No meetings scheduled.</EmptyNote>
                  : view.meetings.map((meeting) => <MeetingCard key={meeting.id} meeting={meeting} />)}
              </div>
            </Panel>
          </div>

          {/* ── Pipeline + Activities + Quick Actions ── */}
          <div className="grid gap-[18px] lg:grid-cols-[1.5fr_1fr]">
            <div className="space-y-[18px]">
              <Panel>
                <SectionHeader
                  title="Sales Pipeline"
                  action={
                    <Link href="/opportunities" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                      View pipeline →
                    </Link>
                  }
                />
                {view.pipeline.length === 0 ? (
                  <EmptyNote>No open pipeline stages are configured.</EmptyNote>
                ) : (
                  <>
                    <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                      {view.pipeline.map((stage) => (
                        <PipelineStageCard key={stage.id} stage={stage} />
                      ))}
                    </div>

                    <div className="bd mt-4 flex items-center justify-between border-t pt-3.5">
                      <span className="txt-muted text-[13px] font-semibold">
                        Total Pipeline Value
                      </span>
                      <span className="txt font-display text-[20px] font-extrabold tracking-tight">
                        {formatMoney(data.pipeline_total, data.pipeline_currency)}
                      </span>
                    </div>
                  </>
                )}
              </Panel>

              <Panel>
                <SectionHeader title="Quick Actions" />
                <div className="grid grid-cols-2 gap-2.5">
                  {QUICK_ACTIONS.map((action) => (
                    <QuickActionButton
                      key={action.label}
                      label={action.label}
                      icon={action.icon}
                      href={action.href}
                      gradient={action.gradient}
                    />
                  ))}
                </div>
              </Panel>
            </div>

            <Panel>
              <SectionHeader
                title="Recent Activities"
                action={
                  <Link href="/meetings" className="flex items-center gap-1 text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                    All activities <ArrowRight className="h-3 w-3" />
                  </Link>
                }
              />
              <div>
                {view.activities.length === 0
                  ? <EmptyNote>No activity recorded yet.</EmptyNote>
                  : view.activities.map((activity, i) => (
                    <ActivityItem
                      key={activity.id}
                      activity={activity}
                      showConnector={i < view.activities.length - 1}
                    />
                  ))}
              </div>
            </Panel>
          </div>
        </>
      )}

    </div>
  );
}

function greeting(now: Date | null): string {
  if (!now) return 'Welcome back';
  const hour = now.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}
