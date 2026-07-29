'use client';

import { Sparkles, FileText, TrendingUp, AlertTriangle, Map } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   AI COMMAND BAR
   Reusable AI actions bar for detail pages.
   ============================================================ */

interface AICommandBarProps {
  className?: string;
}

export default function AICommandBar({ className }: AICommandBarProps) {
  const actions = [
    { label: 'Summarize', icon: FileText, color: 'text-violet-500', bg: 'bg-violet-500/10' },
    { label: 'Predict Win Prob.', icon: TrendingUp, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
    { label: 'Gen. Briefing', icon: FileText, color: 'text-sky-500', bg: 'bg-sky-500/10' },
    { label: 'Next Action', icon: Map, color: 'text-amber-500', bg: 'bg-amber-500/10' },
    { label: 'Identify Risks', icon: AlertTriangle, color: 'text-rose-500', bg: 'bg-rose-500/10' },
  ];

  return (
    <div className={cn('flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-2xl bg-gradient-to-r from-[var(--surface)] to-[var(--surface-2)] border border-[var(--border)]', className)}>
      <div className="flex items-center gap-2 pl-2 pr-4 sm:border-r border-[var(--border)]">
        <Sparkles className="h-5 w-5 text-violet-500" />
        <span className="font-display txt text-[14px] font-bold">Ask AI</span>
      </div>
      <div className="flex flex-wrap items-center gap-2 flex-1">
        {actions.map((action, i) => (
          <button
            key={i}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-2)] transition-colors"
          >
            <div className={cn('flex h-5 w-5 items-center justify-center rounded-md', action.bg)}>
              <action.icon className={cn("h-3 w-3", action.color)} />
            </div>
            <span className="txt text-[12px] font-semibold">{action.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
