'use client';

import { Layers, Mail, Mic, Target, Settings2 } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import FormField, { FormSelect } from '@/components/crm/forms/FormField';

export default function AIFeaturesPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <Layers className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Domain AI Features</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Configure AI behaviors specific to Emails, Meetings, and Sales Intelligence.</p>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="surface bd rounded-2xl border p-5 flex flex-col gap-4">
          <SectionHeader title="Email AI" />
          <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
             <div><p className="txt text-[13px] font-semibold">Draft Emails</p><p className="txt-muted text-[11px] mt-0.5">Allow AI to draft responses from context.</p></div>
             <div className="h-5 w-9 bg-emerald-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
          </div>
          <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
             <div><p className="txt text-[13px] font-semibold">Rewrite Emails</p><p className="txt-muted text-[11px] mt-0.5">Allow AI to improve grammar and tone.</p></div>
             <div className="h-5 w-9 bg-emerald-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
          </div>
          <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
             <div><p className="txt text-[13px] font-semibold">Follow-up Suggestions</p><p className="txt-muted text-[11px] mt-0.5">AI suggests replies when emails go unanswered.</p></div>
             <div className="h-5 w-9 bg-emerald-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5 flex flex-col gap-4">
          <SectionHeader title="Meeting AI" />
          <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
             <div><p className="txt text-[13px] font-semibold">Meeting Summaries</p><p className="txt-muted text-[11px] mt-0.5">Auto-generate notes from meeting transcripts.</p></div>
             <div className="h-5 w-9 bg-emerald-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
          </div>
          <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
             <div><p className="txt text-[13px] font-semibold">Action Items Detection</p><p className="txt-muted text-[11px] mt-0.5">Extract tasks and assign them to attendees.</p></div>
             <div className="h-5 w-9 bg-emerald-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
          </div>
          <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
             <div><p className="txt text-[13px] font-semibold">Sentiment Analysis</p><p className="txt-muted text-[11px] mt-0.5">Analyze attendee sentiment during calls.</p></div>
             <div className="h-5 w-9 bg-[var(--surface)] border border-[var(--border)] rounded-full flex items-center justify-start p-0.5"><div className="h-4 w-4 bg-[var(--muted)] rounded-full" /></div>
          </div>
        </div>

        <div className="md:col-span-2 surface bd rounded-2xl border p-5 flex flex-col gap-6">
          <SectionHeader title="Sales Intelligence Thresholds" />
          
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
             <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] flex flex-col gap-3">
               <div>
                 <p className="txt text-[13px] font-bold mb-1">Lead Scoring</p>
                 <p className="txt-muted text-[11px]">Minimum score required to auto-qualify a lead.</p>
               </div>
               <div className="flex items-center gap-3">
                 <input type="range" className="flex-1 accent-indigo-500" defaultValue="80" />
                 <span className="font-mono text-[12px] font-bold text-indigo-500">80+</span>
               </div>
             </div>

             <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] flex flex-col gap-3">
               <div>
                 <p className="txt text-[13px] font-bold mb-1">Win Probability</p>
                 <p className="txt-muted text-[11px]">Threshold to flag an opportunity as "High Risk".</p>
               </div>
               <div className="flex items-center gap-3">
                 <input type="range" className="flex-1 accent-rose-500" defaultValue="35" />
                 <span className="font-mono text-[12px] font-bold text-rose-500">&lt;35%</span>
               </div>
             </div>

             <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] flex flex-col gap-3">
               <div>
                 <p className="txt text-[13px] font-bold mb-1">Buying Intent</p>
                 <p className="txt-muted text-[11px]">Threshold to notify sales reps of high intent.</p>
               </div>
               <div className="flex items-center gap-3">
                 <input type="range" className="flex-1 accent-emerald-500" defaultValue="90" />
                 <span className="font-mono text-[12px] font-bold text-emerald-500">90+</span>
               </div>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
