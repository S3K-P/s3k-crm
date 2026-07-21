'use client';

import { Cpu, CheckCircle2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import SectionHeader from '@/components/crm/shared/SectionHeader';

const PROVIDERS = [
  { name: 'OpenAI', status: 'Connected', model: 'gpt-4o', apiStatus: 'Operational', icon: 'O' },
  { name: 'Azure OpenAI', status: 'Not Connected', model: '-', apiStatus: '-', icon: 'A' },
  { name: 'Anthropic Claude', status: 'Connected', model: 'claude-3-5-sonnet', apiStatus: 'Operational', icon: 'C' },
  { name: 'Google Gemini', status: 'Not Connected', model: '-', apiStatus: '-', icon: 'G' },
  { name: 'Local LLM', status: 'Not Connected', model: '-', apiStatus: '-', icon: 'L' },
];

const DEFAULT_MODELS = [
  { purpose: 'Chat & Copilot', provider: 'Anthropic Claude', model: 'claude-3-5-sonnet', context: '200k' },
  { purpose: 'Meeting Summaries', provider: 'OpenAI', model: 'gpt-4o', context: '128k' },
  { purpose: 'Email Generation', provider: 'Anthropic Claude', model: 'claude-3-haiku', context: '200k' },
  { purpose: 'Deal Intelligence', provider: 'OpenAI', model: 'gpt-4o', context: '128k' },
];

export default function AIProvidersPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <Cpu className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Providers & Models</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Configure LLM providers and set default models for CRM features.</p>
          </div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {PROVIDERS.map(p => {
          const connected = p.status === 'Connected';
          return (
            <div key={p.name} className={cn("surface bd rounded-2xl border p-5 flex flex-col", connected ? "border-indigo-500/30" : "")}>
              <div className="flex items-start justify-between mb-4">
                <div className="h-10 w-10 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] flex items-center justify-center font-display font-bold text-[16px] txt-muted">
                  {p.icon}
                </div>
                {connected && (
                  <span className="flex items-center gap-1 text-[11px] font-bold text-indigo-500 bg-indigo-500/10 px-2 py-1 rounded-full">
                    <CheckCircle2 className="h-3 w-3" /> Connected
                  </span>
                )}
              </div>
              <div>
                <h3 className="txt text-[15px] font-bold">{p.name}</h3>
                <div className="mt-2 space-y-1">
                  <p className="flex justify-between text-[12px]"><span className="txt-muted">Active Model:</span> <span className="font-semibold txt">{p.model}</span></p>
                  <p className="flex justify-between text-[12px]"><span className="txt-muted">API Status:</span> <span className="font-semibold text-emerald-500">{p.apiStatus}</span></p>
                </div>
              </div>
              <div className="mt-5 pt-4 border-t border-[var(--border)]">
                <button className="w-full py-2 rounded-lg text-[13px] font-semibold bg-[var(--surface-2)] text-[var(--text)] transition hover:bg-[var(--surface)] border border-[var(--border)]">
                  Configure API Keys
                </button>
              </div>
            </div>
          )
        })}
      </div>

      <div className="surface bd rounded-2xl border mt-6">
        <div className="p-5 border-b border-[var(--border)] bg-[var(--surface-2)]">
          <SectionHeader title="Default Model Routing" />
          <p className="txt-muted text-[12px] mt-1">Select which model handles specific AI workloads to optimize for cost and performance.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead className="border-b border-[var(--border)] bg-[var(--surface)]">
              <tr>
                <th className="px-5 py-3 font-bold txt-muted uppercase tracking-wider text-[11px]">Purpose</th>
                <th className="px-5 py-3 font-bold txt-muted uppercase tracking-wider text-[11px]">Provider</th>
                <th className="px-5 py-3 font-bold txt-muted uppercase tracking-wider text-[11px]">Model</th>
                <th className="px-5 py-3 font-bold txt-muted uppercase tracking-wider text-[11px]">Context</th>
                <th className="px-5 py-3 font-bold txt-muted uppercase tracking-wider text-[11px] text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {DEFAULT_MODELS.map(m => (
                <tr key={m.purpose} className="hover:bg-[var(--surface-2)] transition-colors">
                  <td className="px-5 py-3 font-semibold txt">{m.purpose}</td>
                  <td className="px-5 py-3 txt">{m.provider}</td>
                  <td className="px-5 py-3 font-mono text-[11px] bg-[var(--surface-2)] rounded px-2">{m.model}</td>
                  <td className="px-5 py-3 txt-muted">{m.context}</td>
                  <td className="px-5 py-3 text-right">
                    <button className="text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">Change Model</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
