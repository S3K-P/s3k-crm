'use client';

import { FileText, BarChart3, Palette, Play, Info } from 'lucide-react';

/**
 * Right "Recent" rail — in the real app this lists the project's latest
 * items from the API. The template ships static demo data:
 * replace DEMO_RECENT with your own fetch when wiring a backend.
 */
const DEMO_RECENT = [
  { id: '1', title: 'Quarterly summary',      label: 'Document', icon: FileText,  grad: '#7c3aed,#4f46e5', when: '2h ago' },
  { id: '2', title: 'Team intro walkthrough', label: 'Media',    icon: Play,      grad: '#0ea5e9,#2563eb', when: '5h ago' },
  { id: '3', title: 'Monthly metrics',        label: 'Report',   icon: BarChart3, grad: '#ec4899,#f43f5e', when: '1d ago' },
  { id: '4', title: 'Brand style sheet',      label: 'Design',   icon: Palette,   grad: '#f59e0b,#f97316', when: '2d ago' },
];

export default function RecentRail() {
  return (
    <aside className="surface bd hidden w-[320px] shrink-0 flex-col overflow-y-auto border-l xl:flex">
      <div className="flex items-center justify-between p-4 pb-2">
        <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">Recent in this project</span>
        <button className="text-[11px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>See all</button>
      </div>

      <div className="space-y-2.5 px-3">
        {DEMO_RECENT.map((a) => (
          <button key={a.id} className="ctl flex w-full items-center gap-3 overflow-hidden rounded-xl px-3 py-2.5 text-left transition hover:surface-2">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg" style={{ background: `linear-gradient(135deg,${a.grad})` }}>
              <a.icon className="h-3.5 w-3.5 text-white/90" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="txt truncate text-[12px] font-semibold leading-tight">{a.title}</div>
              <div className="txt-faint mt-0.5 text-[10.5px]">{a.label} · {a.when}</div>
            </div>
          </button>
        ))}
      </div>

      <div className="ctl m-3 mt-4 rounded-xl p-3 text-[11.5px] leading-snug" style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
        <span className="mb-1 flex items-center gap-1.5 font-semibold" style={{ color: 'var(--accent)' }}>
          <Info className="h-3.5 w-3.5" /> Tip
        </span>
        <span className="txt-muted">Finished items appear here automatically.</span>
      </div>
    </aside>
  );
}
