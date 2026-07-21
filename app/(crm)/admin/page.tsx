'use client';

import { Users, LayoutList, Workflow, Blocks, ShieldCheck, Activity } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import ActivityItem from '@/components/crm/cards/ActivityItem';

const STATS = [
  { label: 'Total Users', value: '1,245', icon: Users, color: 'text-sky-500', bg: 'bg-sky-500/10' },
  { label: 'Active Users', value: '1,180', icon: Activity, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  { label: 'Teams', value: '45', icon: Workflow, color: 'text-violet-500', bg: 'bg-violet-500/10' },
  { label: 'Active Pipelines', value: '8', icon: LayoutList, color: 'text-amber-500', bg: 'bg-amber-500/10' },
  { label: 'Connected Integrations', value: '12', icon: Blocks, color: 'text-rose-500', bg: 'bg-rose-500/10' },
  { label: 'System Health', value: '99.9%', icon: ShieldCheck, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
];

const MOCK_ADMIN_ACTIVITY = [
  { id: '1', icon: ShieldCheck, iconGradient: 'from-sky-500 to-blue-600', title: 'Role Updated', detail: 'Admin modified "Sales Rep" permissions.', timestamp: '10 mins ago' },
  { id: '2', icon: Users, iconGradient: 'from-amber-500 to-orange-500', title: 'New User Provisioned', detail: 'Alice Smith was added to the CRM.', timestamp: '1 hour ago' },
  { id: '3', icon: Blocks, iconGradient: 'from-emerald-500 to-green-600', title: 'Integration Sync', detail: 'Salesforce data import completed.', timestamp: '2 hours ago' },
];

export default function AdminDashboardPage() {
  return (
    <div className="flex flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div>
        <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">Admin Dashboard</h1>
        <p className="txt-muted mt-1 text-[13.5px]">Overview of system health, usage, and recent configurations.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {STATS.map(stat => (
          <div key={stat.label} className="surface bd rounded-xl border p-5 flex items-start gap-4">
            <div className={`h-10 w-10 shrink-0 rounded-lg flex items-center justify-center ${stat.bg}`}>
              <stat.icon className={`h-5 w-5 ${stat.color}`} />
            </div>
            <div>
              <p className="txt-muted text-[11px] font-bold uppercase tracking-wider">{stat.label}</p>
              <p className="font-display txt text-[24px] font-bold mt-1 leading-none">{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-6 pt-4">
         <div className="surface bd rounded-2xl border p-5">
           <SectionHeader title="Recent Admin Activity" />
           <div className="pt-4">
             {MOCK_ADMIN_ACTIVITY.map((act, i) => (
               <ActivityItem key={act.id} activity={act} showConnector={i < MOCK_ADMIN_ACTIVITY.length - 1} />
             ))}
           </div>
         </div>

         <div className="surface bd rounded-2xl border p-5 bg-gradient-to-br from-[var(--surface-2)] to-[var(--surface)]">
           <SectionHeader title="System Status" />
           <div className="flex flex-col gap-4 pt-4">
             <div className="flex items-center justify-between">
               <span className="txt text-[13px] font-medium">Database Latency</span>
               <span className="text-[12px] font-mono text-emerald-500">12ms</span>
             </div>
             <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
               <span className="txt text-[13px] font-medium">API Rate Limit Usage</span>
               <span className="text-[12px] font-mono txt-muted">45% (3,400/hr)</span>
             </div>
             <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
               <span className="txt text-[13px] font-medium">Storage Capacity</span>
               <span className="text-[12px] font-mono txt-muted">62% (1.2TB)</span>
             </div>
             <div className="mt-4 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 flex items-start gap-3">
               <ShieldCheck className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
               <p className="text-[12px] text-amber-700 dark:text-amber-400">Routine maintenance scheduled for Sunday at 02:00 AM UTC. Expect 5 minutes of read-only mode.</p>
             </div>
           </div>
         </div>
      </div>
    </div>
  );
}
