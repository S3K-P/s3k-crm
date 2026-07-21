'use client';

import { ShieldCheck, BarChart, HardDrive, KeyRound } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';

export default function AISecurityAnalyticsPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <ShieldCheck className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Security & Analytics</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Manage AI compliance policies and review platform consumption metrics.</p>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        
        {/* Security Section */}
        <div className="flex flex-col gap-6">
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Enterprise AI Controls" />
            <div className="mt-5 space-y-3">
               <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                 <div>
                   <p className="txt text-[13px] font-semibold flex items-center gap-2"><HardDrive className="h-4 w-4" /> Data Retention</p>
                   <p className="txt-muted text-[11px] mt-0.5">Prompt history is purged after 30 days.</p>
                 </div>
                 <button className="text-[12px] font-semibold text-[var(--accent)]">Configure</button>
               </div>
               <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                 <div>
                   <p className="txt text-[13px] font-semibold flex items-center gap-2"><KeyRound className="h-4 w-4" /> PII Masking</p>
                   <p className="txt-muted text-[11px] mt-0.5">Auto-redact emails, phones, and SSNs from prompts.</p>
                 </div>
                 <div className="h-5 w-9 bg-indigo-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
               </div>
               <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                 <div>
                   <p className="txt text-[13px] font-semibold">Audit AI Activity</p>
                   <p className="txt-muted text-[11px] mt-0.5">Log all AI requests to external providers.</p>
                 </div>
                 <div className="h-5 w-9 bg-indigo-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
               </div>
               <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                 <div>
                   <p className="txt text-[13px] font-semibold">Human Approval Required</p>
                   <p className="txt-muted text-[11px] mt-0.5">Require review for bulk AI email sending.</p>
                 </div>
                 <div className="h-5 w-9 bg-indigo-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
               </div>
            </div>
          </div>
        </div>

        {/* Analytics Section */}
        <div className="flex flex-col gap-6">
          <div className="surface bd rounded-2xl border p-5 bg-gradient-to-br from-[var(--surface-2)] to-[var(--surface)]">
            <SectionHeader title="Usage & Analytics" />
            
            <div className="mt-6 space-y-6">
              
              <div className="grid grid-cols-2 gap-4">
                 <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 text-center">
                   <p className="text-[11px] font-bold uppercase tracking-wider txt-muted mb-1">Token Consumption</p>
                   <p className="font-display txt text-[24px] font-bold text-indigo-500">12.4M</p>
                   <p className="text-[10px] txt-muted mt-1">Current billing cycle</p>
                 </div>
                 <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 text-center">
                   <p className="text-[11px] font-bold uppercase tracking-wider txt-muted mb-1">Cost Estimate</p>
                   <p className="font-display txt text-[24px] font-bold text-rose-500">$342.50</p>
                   <p className="text-[10px] txt-muted mt-1">Current billing cycle</p>
                 </div>
              </div>

              <div className="space-y-4 pt-2">
                <div>
                  <div className="flex items-center justify-between text-[12px] font-semibold txt-muted mb-1.5">
                    <span>Most Used Model (GPT-4o)</span>
                    <span>68%</span>
                  </div>
                  <div className="h-1.5 w-full bg-[var(--surface)] rounded-full overflow-hidden border border-[var(--border)]">
                    <div className="h-full bg-indigo-500" style={{ width: '68%' }} />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between text-[12px] font-semibold txt-muted mb-1.5">
                    <span>Most Used Feature (Summaries)</span>
                    <span>42%</span>
                  </div>
                  <div className="h-1.5 w-full bg-[var(--surface)] rounded-full overflow-hidden border border-[var(--border)]">
                    <div className="h-full bg-emerald-500" style={{ width: '42%' }} />
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
