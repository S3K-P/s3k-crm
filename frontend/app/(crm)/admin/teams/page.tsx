'use client';

import { UsersRound, Plus, MoreHorizontal } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';

const TEAMS = [
  { name: 'Enterprise Sales', manager: 'Mike Johnson', members: 12, pipeline: 'Enterprise Deals' },
  { name: 'SMB East', manager: 'Priya Patel', members: 8, pipeline: 'Standard Pipeline' },
  { name: 'SDR Team A', manager: 'Sarah Chen', members: 15, pipeline: 'Inbound Leads' },
];

export default function AdminTeamsPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-5xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-emerald-500 to-teal-600">
            <UsersRound className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Teams</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Organize users into reporting structures.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            <Plus className="h-4 w-4" /> Create Team
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {TEAMS.map(team => (
          <div key={team.name} className="surface bd rounded-2xl border p-5 relative">
            <button className="absolute top-4 right-4 text-[var(--muted)] hover:text-[var(--text)]">
              <MoreHorizontal className="h-4 w-4" />
            </button>
            <h3 className="txt text-[15px] font-bold">{team.name}</h3>
            <p className="txt-muted text-[12px] mt-1">Managed by {team.manager}</p>
            
            <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center justify-between">
              <div>
                <p className="txt-muted text-[10px] font-semibold uppercase tracking-wider">Members</p>
                <p className="txt text-[14px] font-bold mt-0.5">{team.members}</p>
              </div>
              <div className="text-right">
                <p className="txt-muted text-[10px] font-semibold uppercase tracking-wider">Pipeline</p>
                <p className="txt text-[13px] font-semibold text-[var(--accent)] mt-0.5">{team.pipeline}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
