'use client';

import { BrainCircuit, Settings, PlayCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import StatusBadge from '@/components/crm/shared/StatusBadge';

const AGENTS = [
  { name: 'Sales Coach', desc: 'Analyzes call transcripts and provides personalized feedback for reps.', status: 'Active', lastRun: '10 mins ago' },
  { name: 'Lead Qualifier', desc: 'Automatically scores and categorizes incoming leads based on BANT.', status: 'Active', lastRun: '2 mins ago' },
  { name: 'Meeting Assistant', desc: 'Joins calls, transcribes, and extracts action items into the CRM.', status: 'Active', lastRun: '1 hour ago' },
  { name: 'Proposal Generator', desc: 'Drafts custom proposals using CRM data and product documentation.', status: 'Paused', lastRun: 'Yesterday' },
  { name: 'Executive Brief Generator', desc: 'Compiles weekly account health summaries for leadership.', status: 'Active', lastRun: '3 days ago' },
  { name: 'Follow-up Assistant', desc: 'Drafts context-aware follow-up emails after meetings.', status: 'Active', lastRun: '15 mins ago' },
  { name: 'Forecast Analyst', desc: 'Predicts pipeline closure probability based on historical data.', status: 'Paused', lastRun: '1 week ago' },
  { name: 'CRM Copilot', desc: 'Global conversational assistant available across all CRM pages.', status: 'Active', lastRun: 'Just now' },
];

export default function AIAgentsPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <BrainCircuit className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Autonomous AI Agents</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Manage specialized AI agents that run in the background to assist your team.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            Deploy Custom Agent
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {AGENTS.map(agent => {
          const isActive = agent.status === 'Active';
          return (
            <div key={agent.name} className={cn("surface bd rounded-2xl border p-5 flex flex-col", isActive ? "border-indigo-500/20" : "opacity-80 grayscale-[20%]")}>
              <div className="flex items-start justify-between mb-2">
                <h3 className="txt text-[15px] font-bold leading-tight">{agent.name}</h3>
                <StatusBadge label={agent.status} variant={isActive ? 'success' : 'neutral'} />
              </div>
              <p className="txt-muted text-[12.5px] leading-relaxed mb-4 flex-1">{agent.desc}</p>
              
              <div className="flex items-center justify-between text-[11px] txt-muted mb-4 font-medium">
                <span>Last Run:</span>
                <span>{agent.lastRun}</span>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-auto">
                <button className={cn("flex items-center justify-center gap-2 py-2 rounded-lg text-[12.5px] font-semibold transition-colors", isActive ? "bg-[var(--surface-2)] text-[var(--text)] hover:bg-rose-500/10 hover:text-rose-500 border border-[var(--border)]" : "bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 border border-emerald-500/20")}>
                  {isActive ? 'Pause' : 'Enable'}
                </button>
                <button className="flex items-center justify-center gap-2 py-2 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] text-[var(--text)] hover:border-[var(--accent)] transition-colors text-[12.5px] font-semibold">
                  <Settings className="h-3.5 w-3.5" /> Configure
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  );
}
