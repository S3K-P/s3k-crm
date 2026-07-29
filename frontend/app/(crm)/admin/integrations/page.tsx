'use client';

import { Blocks, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const INTEGRATIONS = [
  { name: 'Microsoft 365', category: 'Email & Calendar', connected: true, icon: 'M' },
  { name: 'Google Workspace', category: 'Email & Calendar', connected: false, icon: 'G' },
  { name: 'Slack', category: 'Communication', connected: true, icon: 'S' },
  { name: 'Microsoft Teams', category: 'Communication', connected: false, icon: 'T' },
  { name: 'Zoom', category: 'Meetings', connected: true, icon: 'Z' },
  { name: 'Salesforce Import', category: 'Data Migration', connected: false, icon: 'SF' },
];

export default function AdminIntegrationsPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-pink-500 to-rose-600">
            <Blocks className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Integrations</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Connect your CRM to external services.</p>
          </div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {INTEGRATIONS.map(int => (
          <div key={int.name} className={cn("surface bd rounded-2xl border p-5 flex flex-col", int.connected ? "border-emerald-500/30" : "")}>
            <div className="flex items-start justify-between mb-4">
              <div className="h-12 w-12 rounded-xl bg-[var(--surface-2)] border border-[var(--border)] flex items-center justify-center font-display font-bold text-[18px] txt-muted">
                {int.icon}
              </div>
              {int.connected && (
                <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded-full">
                  <CheckCircle2 className="h-3 w-3" /> Connected
                </span>
              )}
            </div>
            <div>
              <h3 className="txt text-[15px] font-bold">{int.name}</h3>
              <p className="txt-muted text-[12px] mt-1">{int.category}</p>
            </div>
            <div className="mt-auto pt-5">
              <button className={cn("w-full py-2 rounded-lg text-[13px] font-semibold transition-colors", int.connected ? "bg-[var(--surface-2)] text-[var(--text)] hover:bg-rose-500/10 hover:text-rose-500" : "bg-[var(--text)] text-[var(--bg)] hover:opacity-90")}>
                {int.connected ? 'Disconnect' : 'Connect'}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
