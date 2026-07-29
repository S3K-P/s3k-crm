'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  UserPlus, CalendarDays, Target, Building2,
  Users, CheckCircle2, DollarSign, ClipboardList,
  Phone, Mail, FileText, Handshake, NotebookPen,
  ArrowRight,
} from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import KpiCard from '@/components/crm/cards/KpiCard';
import TaskCard, { type TaskItem } from '@/components/crm/cards/TaskCard';
import MeetingCard, { type MeetingItem } from '@/components/crm/cards/MeetingCard';
import PipelineStageCard, { type PipelineStage } from '@/components/crm/cards/PipelineStageCard';
import ActivityItem, { type ActivityEntry } from '@/components/crm/cards/ActivityItem';
import QuickActionButton from '@/components/crm/cards/QuickActionButton';

/* ============================================================
   MOCK DATA — replace with API calls when backend is ready
   ============================================================ */

const MOCK_TASKS: TaskItem[] = [
  { id: '1', title: 'Follow up with Acme Corp',      description: 'Send updated proposal after call',        priority: 'high',   dueTime: '10:00 AM', relatedTo: 'Acme Corp',      completed: false },
  { id: '2', title: 'Prepare demo for TechVista',     description: 'Product walkthrough for their CTO',       priority: 'high',   dueTime: '11:30 AM', relatedTo: 'TechVista Inc',   completed: false },
  { id: '3', title: 'Update contact info for Globex', description: 'New phone number from last meeting',       priority: 'medium', dueTime: '1:00 PM',  relatedTo: 'Globex Ltd',     completed: false },
  { id: '4', title: 'Review Q3 pipeline forecast',    description: 'Validate numbers with sales team',         priority: 'medium', dueTime: '3:00 PM',  completed: false },
  { id: '5', title: 'Send NDA to BlueStar',           description: 'Legal approved — ready for signature',     priority: 'low',    dueTime: '4:30 PM',  relatedTo: 'BlueStar Inc',   completed: false },
];

const MOCK_MEETINGS: MeetingItem[] = [
  { id: '1', title: 'Discovery Call — Acme Corp',        time: '10:00 AM – 10:30 AM', company: 'Acme Corp',     contact: 'Sarah Chen',     status: 'upcoming' },
  { id: '2', title: 'Product Demo — TechVista',          time: '11:30 AM – 12:15 PM', company: 'TechVista Inc', contact: 'James Rodriguez', status: 'upcoming' },
  { id: '3', title: 'Contract Review — Globex',          time: '2:00 PM – 2:45 PM',   company: 'Globex Ltd',    contact: 'Priya Patel',    status: 'upcoming' },
  { id: '4', title: 'Quarterly Review — Initech',        time: '4:00 PM – 4:30 PM',   company: 'Initech',       contact: 'Mike Johnson',   status: 'upcoming' },
];

const MOCK_PIPELINE: PipelineStage[] = [
  { id: '1', label: 'Prospecting',    count: 24, value: '$180K', percentage: 85, gradient: 'from-sky-500 to-blue-600' },
  { id: '2', label: 'Qualification',  count: 18, value: '$320K', percentage: 70, gradient: 'from-violet-600 to-indigo-600' },
  { id: '3', label: 'Proposal',       count: 12, value: '$540K', percentage: 55, gradient: 'from-amber-500 to-orange-500' },
  { id: '4', label: 'Negotiation',    count: 8,  value: '$410K', percentage: 40, gradient: 'from-pink-500 to-rose-500' },
  { id: '5', label: 'Closed Won',     count: 6,  value: '$290K', percentage: 100, gradient: 'from-emerald-500 to-green-600' },
];

const MOCK_ACTIVITIES: ActivityEntry[] = [
  { id: '1', icon: Phone,        iconGradient: 'from-emerald-500 to-green-600', title: 'Call completed with Sarah Chen',         detail: 'Discussed pricing for Q3 renewal — Acme Corp', timestamp: '25 min ago' },
  { id: '2', icon: Mail,         iconGradient: 'from-sky-500 to-blue-600',      title: 'Email sent to James Rodriguez',          detail: 'Product demo follow-up deck — TechVista Inc',   timestamp: '1 hour ago' },
  { id: '3', icon: Handshake,    iconGradient: 'from-violet-600 to-indigo-600', title: 'New opportunity created',                detail: '$120K deal — Globex Ltd Enterprise plan',       timestamp: '2 hours ago' },
  { id: '4', icon: NotebookPen,  iconGradient: 'from-amber-500 to-orange-500',  title: 'Meeting notes added',                    detail: 'Weekly pipeline review with sales team',        timestamp: '3 hours ago' },
  { id: '5', icon: UserPlus,     iconGradient: 'from-pink-500 to-rose-500',     title: 'New lead captured',                      detail: 'Mike Johnson from Initech — Website form',      timestamp: '4 hours ago' },
  { id: '6', icon: FileText,     iconGradient: 'from-emerald-500 to-green-600', title: 'Proposal sent to Priya Patel',           detail: 'Enterprise tier annual contract — Globex Ltd',  timestamp: '5 hours ago' },
];

const QUICK_ACTIONS = [
  { label: 'Add New Lead',        icon: UserPlus,     href: '/leads',         gradient: 'from-emerald-500 to-green-600' },
  { label: 'Schedule Meeting',    icon: CalendarDays, href: '/meetings',      gradient: 'from-sky-500 to-blue-600' },
  { label: 'Create Opportunity',  icon: Target,       href: '/opportunities', gradient: 'from-violet-600 to-indigo-600' },
  { label: 'Add Account',         icon: Building2,    href: '/accounts',      gradient: 'from-amber-500 to-orange-500' },
];

/* ============================================================
   HELPERS
   ============================================================ */

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

function getFormattedDate(): string {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/* ============================================================
   DASHBOARD PAGE
   ============================================================ */

export default function DashboardPage() {
  const [tasks, setTasks] = useState(MOCK_TASKS);

  const handleToggleTask = (id: string) => {
    setTasks(prev =>
      prev.map(t => (t.id === id ? { ...t, completed: !t.completed } : t)),
    );
  };

  return (
    <div className="space-y-6 p-6 lg:p-8">

      {/* ── Page Header ── */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1
            className="font-display text-[22px] font-extrabold leading-tight tracking-tight"
            style={{ color: 'var(--text)' }}
          >
            {getGreeting()} 👋
          </h1>
          <p className="txt-muted mt-0.5 text-[13px] font-medium">
            Here&apos;s what&apos;s happening with your sales pipeline today
          </p>
        </div>
        <p className="txt-faint text-[12.5px] font-medium">{getFormattedDate()}</p>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 gap-3.5 md:grid-cols-3 xl:grid-cols-6">
        <KpiCard href="/leads" label="New Leads"          value="42"      delta="+12% this week" trend="up"   icon={Users}          iconGradient="from-emerald-500 to-green-600" />
        <KpiCard href="/qualification" label="Qualified"          value="18"      delta="+8% this week"  trend="up"   icon={CheckCircle2}   iconGradient="from-violet-600 to-indigo-600" />
        <KpiCard href="/opportunities" label="Open Opps"          value="27"      delta="3 closing soon" trend="flat" icon={Target}         iconGradient="from-sky-500 to-blue-600" />
        <KpiCard href="/opportunities" label="Pipeline Value"     value="$1.74M"  delta="+$230K vs last" trend="up"   icon={DollarSign}     iconGradient="from-amber-500 to-orange-500" />
        <KpiCard href="/meetings" label="Meetings Today"     value="4"       delta="Next at 10:00"  trend="flat" icon={CalendarDays}   iconGradient="from-pink-500 to-rose-500" />
        <KpiCard label="Tasks Due"          value="5"       delta="2 high priority" trend="flat" icon={ClipboardList} iconGradient="from-violet-500 to-purple-600" />
      </div>

      {/* ── Middle Row: Tasks + Meetings ── */}
      <div className="grid gap-[18px] lg:grid-cols-2">
        {/* Today's Tasks */}
        <div className="surface bd rounded-2xl border p-[18px]">
          <SectionHeader
            title="Today's Tasks"
            action={
              <Link href="/leads" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                View all →
              </Link>
            }
          />
          <div className="space-y-2">
            {tasks.map(task => (
              <TaskCard key={task.id} task={task} onToggle={handleToggleTask} />
            ))}
          </div>
        </div>

        {/* Upcoming Meetings */}
        <div className="surface bd rounded-2xl border p-[18px]">
          <SectionHeader
            title="Upcoming Meetings"
            action={
              <Link href="/meetings" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                View all →
              </Link>
            }
          />
          <div className="space-y-2">
            {MOCK_MEETINGS.map(meeting => (
              <MeetingCard key={meeting.id} meeting={meeting} />
            ))}
          </div>
        </div>
      </div>

      {/* ── Pipeline + Activities + Quick Actions ── */}
      <div className="grid gap-[18px] lg:grid-cols-[1.5fr_1fr]">
        {/* Left column: Pipeline + Quick Actions stacked */}
        <div className="space-y-[18px]">
          {/* Sales Pipeline Summary */}
          <div className="surface bd rounded-2xl border p-[18px]">
            <SectionHeader
              title="Sales Pipeline"
              action={
                <Link href="/opportunities" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                  View pipeline →
                </Link>
              }
            />
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
              {MOCK_PIPELINE.map(stage => (
                <PipelineStageCard key={stage.id} stage={stage} />
              ))}
            </div>

            {/* Pipeline total */}
            <div className="bd mt-4 flex items-center justify-between border-t pt-3.5">
              <span className="txt-muted text-[13px] font-semibold">Total Pipeline Value</span>
              <span className="txt font-display text-[20px] font-extrabold tracking-tight">$1.74M</span>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="surface bd rounded-2xl border p-[18px]">
            <SectionHeader title="Quick Actions" />
            <div className="grid grid-cols-2 gap-2.5">
              {QUICK_ACTIONS.map(action => (
                <QuickActionButton
                  key={action.label}
                  label={action.label}
                  icon={action.icon}
                  href={action.href}
                  gradient={action.gradient}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Right column: Recent Activities */}
        <div className="surface bd rounded-2xl border p-[18px]">
          <SectionHeader
            title="Recent Activities"
            action={
              <button className="flex items-center gap-1 text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>
                All activities <ArrowRight className="h-3 w-3" />
              </button>
            }
          />
          <div>
            {MOCK_ACTIVITIES.map((activity, i) => (
              <ActivityItem
                key={activity.id}
                activity={activity}
                showConnector={i < MOCK_ACTIVITIES.length - 1}
              />
            ))}
          </div>
        </div>
      </div>

    </div>
  );
}
