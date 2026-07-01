'use client';

import { type LucideIcon } from 'lucide-react';

interface PageHeaderProps {
  icon?: LucideIcon;
  title: string;
  subtitle?: string;
  /** Right-side slot: e.g. a Save button */
  action?: React.ReactNode;
}

/**
 * Dark title banner at the top of every app page (below the Header top bar).
 * Title + subtitle + optional right-side action only — no layout changes below.
 */
export default function PageHeader({ icon: Icon, title, subtitle, action }: PageHeaderProps) {
  return (
    <div className="border-b border-white/10 bg-gradient-to-br from-[#1a1330] via-[#1e1640] to-[#1a1330] px-6 py-5 text-white">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          {Icon && (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-white/10 ring-1 ring-white/20">
              <Icon className="h-5 w-5 text-violet-200" />
            </div>
          )}
          <div>
            <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight">{title}</h1>
            {subtitle && (
              <p className="mt-0.5 text-[13px] font-medium text-violet-200/70">{subtitle}</p>
            )}
          </div>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    </div>
  );
}
