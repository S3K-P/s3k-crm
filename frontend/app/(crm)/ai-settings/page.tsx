'use client';

import { Activity, Bot, Zap, Target, Mail, ShieldAlert } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';

const KPI_CARDS = [
  { label: 'AI Requests Today', value: '14,285', icon: Zap, color: 'text-sky-500', bg: 'bg-sky-500/10' },
  { label: 'Summaries Generated', value: '4,192', icon: Activity, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  { label: 'Opportunities Assisted', value: '840', icon: Target, color: 'text-violet-500', bg: 'bg-violet-500/10' },
  { label: 'Meetings Summarized', value: '315', icon: Bot, color: 'text-amber-500', bg: 'bg-amber-500/10' },
  { label: 'Emails Generated', value: '8,401', icon: Mail, color: 'text-indigo-500', bg: 'bg-indigo-500/10' },
  { label: 'Active AI Agents', value: '6', icon: Bot, color: 'text-rose-500', bg: 'bg-rose-500/10' },
];

export default function AISettingsDashboard() {
  return (
    <div className="flex flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div>
        <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">AI Overview</h1>
        <p className="txt-muted mt-1 text-[13.5px]">Monitor platform utilization and core AI performance metrics.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {KPI_CARDS.map(stat => (
          <div key={stat.label} className="surface bd rounded-xl border p-5 flex flex-col sm:flex-row sm:items-center gap-4">
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
           <SectionHeader title="Platform Adoption" />
           <div className="flex h-48 items-end gap-2 pt-6 pb-2">
             {/* Mock chart bars */}
             {[40, 55, 45, 60, 75, 65, 85, 80, 95].map((val, i) => (
               <div key={i} className="flex-1 bg-[var(--accent)]/20 hover:bg-[var(--accent)] transition-colors rounded-t-sm" style={{ height: `${val}%` }} />
             ))}
           </div>
           <div className="flex justify-between mt-2">
             <span className="txt-muted text-[11px]">Last 7 Days</span>
             <span className="txt-muted text-[11px]">+24% vs previous</span>
           </div>
         </div>

         <div className="surface bd rounded-2xl border p-5 bg-gradient-to-br from-[var(--surface-2)] to-[var(--surface)] flex flex-col">
           <SectionHeader title="AI System Health" />
           <div className="flex flex-col gap-4 pt-4 flex-1">
             <div className="flex items-center justify-between">
               <span className="txt text-[13px] font-medium">Model Latency (Avg)</span>
               <span className="text-[12px] font-mono text-emerald-500">850ms</span>
             </div>
             <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
               <span className="txt text-[13px] font-medium">Token Rate Limit</span>
               <div className="flex items-center gap-2">
                 <div className="w-24 h-1.5 bg-[var(--surface)] rounded-full overflow-hidden border border-[var(--border)]">
                   <div className="h-full bg-amber-500 w-[65%]" />
                 </div>
                 <span className="text-[12px] font-mono txt-muted">65%</span>
               </div>
             </div>
             <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
               <span className="txt text-[13px] font-medium">Knowledge Base Sync</span>
               <span className="text-[12px] font-medium text-emerald-500 flex items-center gap-1">Synced 2m ago</span>
             </div>
             <div className="mt-auto p-3 rounded-lg border border-[var(--border)] bg-[var(--bg)] flex items-start gap-3">
               <ShieldAlert className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
               <p className="text-[12px] txt-muted leading-relaxed">All AI providers are operating normally. No anomalies detected in prompt filtering or PII masking.</p>
             </div>
           </div>
         </div>
      </div>
    </div>
  );
}
