'use client';

import { Zap, Play, CheckCircle2 } from 'lucide-react';

const AUTOMATIONS = [
  { name: 'Auto summarize meetings', trigger: 'Meeting Concluded', action: 'Generate Transcript & Action Items', enabled: true },
  { name: 'Auto qualify leads', trigger: 'New Lead Created', action: 'Score using BANT & AI Copilot', enabled: true },
  { name: 'Generate follow-up emails', trigger: 'Meeting Summarized', action: 'Draft Follow-up Template', enabled: true },
  { name: 'Notify sales managers of risky deals', trigger: 'Deal Health < 40', action: 'Send Slack Alert', enabled: false },
  { name: 'Generate executive briefs', trigger: 'Every Friday 5PM', action: 'Compile Weekly Report', enabled: true },
  { name: 'Recommend next best actions', trigger: 'Opportunity Stage Changed', action: 'Push Suggestion to UI', enabled: true },
];

export default function AIAutomationsPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Automations & Workflows</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Configure AI-driven automated workflows based on CRM triggers.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            Create Workflow
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {AUTOMATIONS.map(auto => (
          <div key={auto.name} className="surface bd rounded-2xl border p-5 flex flex-col">
             <div className="flex items-start justify-between mb-4">
                <div className="h-10 w-10 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] flex items-center justify-center">
                  <Play className="h-4 w-4 text-[var(--accent)]" />
                </div>
                {auto.enabled && (
                  <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded-full">
                    <CheckCircle2 className="h-3 w-3" /> Active
                  </span>
                )}
             </div>
             
             <h3 className="txt text-[15px] font-bold">{auto.name}</h3>
             
             <div className="mt-4 pt-4 border-t border-[var(--border)] space-y-3">
               <div>
                 <p className="text-[10px] uppercase font-bold tracking-wider txt-muted mb-0.5">When (Trigger)</p>
                 <p className="text-[13px] font-medium txt">{auto.trigger}</p>
               </div>
               <div>
                 <p className="text-[10px] uppercase font-bold tracking-wider txt-muted mb-0.5">Then (Action)</p>
                 <p className="text-[13px] font-medium txt">{auto.action}</p>
               </div>
             </div>
          </div>
        ))}
      </div>
    </div>
  );
}
