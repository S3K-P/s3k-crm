'use client';

import { Settings, GitMerge, DollarSign, Globe2, Mail } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';

export default function AdminCRMSettingsPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-5xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-slate-600 to-gray-800">
            <Settings className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">CRM Settings</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Core system configurations and localization.</p>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Pipelines & Stages" />
          <div className="mt-4 space-y-3">
             <button className="w-full flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--accent)] transition-colors">
               <span className="txt text-[13px] font-semibold">Sales Pipelines</span>
               <span className="txt-muted text-[12px]">2 Active</span>
             </button>
             <button className="w-full flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--accent)] transition-colors">
               <span className="txt text-[13px] font-semibold">Opportunity Stages</span>
               <span className="txt-muted text-[12px]">7 Stages</span>
             </button>
             <button className="w-full flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--accent)] transition-colors">
               <span className="txt text-[13px] font-semibold">Lead Statuses</span>
               <span className="txt-muted text-[12px]">5 Statuses</span>
             </button>
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Localization" />
          <div className="mt-4 space-y-3">
             <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
               <div>
                 <p className="txt text-[13px] font-semibold">Base Currency</p>
                 <p className="txt-muted text-[11px] mt-0.5">Used for all pipeline rollups.</p>
               </div>
               <span className="px-2 py-1 bg-[var(--surface)] border border-[var(--border)] rounded text-[12px] font-bold">USD ($)</span>
             </div>
             <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
               <div>
                 <p className="txt text-[13px] font-semibold">System Time Zone</p>
                 <p className="txt-muted text-[11px] mt-0.5">Default for new users.</p>
               </div>
               <span className="px-2 py-1 bg-[var(--surface)] border border-[var(--border)] rounded text-[12px] font-bold">UTC-8</span>
             </div>
          </div>
        </div>
        
        <div className="surface bd rounded-2xl border p-5 md:col-span-2">
          <SectionHeader title="Email Templates" />
          <div className="mt-4 grid sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
              <h4 className="txt text-[13px] font-bold">Meeting Follow-up</h4>
              <p className="txt-muted text-[11px] mt-1">Last updated 2 days ago</p>
              <button className="mt-3 text-[12px] font-semibold text-[var(--accent)]">Edit Template</button>
            </div>
            <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
              <h4 className="txt text-[13px] font-bold">Cold Outreach V1</h4>
              <p className="txt-muted text-[11px] mt-1">Last updated 1 week ago</p>
              <button className="mt-3 text-[12px] font-semibold text-[var(--accent)]">Edit Template</button>
            </div>
            <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] border-dashed flex items-center justify-center cursor-pointer hover:bg-[var(--surface)] transition-colors">
              <span className="txt text-[13px] font-semibold">+ Create Template</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
