'use client';

import { cn } from '@/lib/utils';
import { ReactNode, useState } from 'react';

/* ============================================================
   TABS
   Reusable Tabs component for detail views.
   ============================================================ */

export interface TabDef {
  id: string;
  label: string;
  content: ReactNode;
}

interface TabsProps {
  tabs: TabDef[];
  defaultTab?: string;
  className?: string;
}

export default function Tabs({ tabs, defaultTab, className }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs[0]?.id);

  return (
    <div className={cn('flex flex-col', className)}>
      <div className="border-b border-[var(--border)]">
        <div className="flex space-x-6 px-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'whitespace-nowrap border-b-2 py-3 text-[13.5px] font-semibold transition-colors',
                activeTab === tab.id
                  ? 'border-[var(--accent)] text-[var(--accent)]'
                  : 'border-transparent text-[var(--muted)] hover:border-[var(--border)] hover:text-[var(--text)]'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      
      <div className="pt-5">
        {tabs.find(t => t.id === activeTab)?.content}
      </div>
    </div>
  );
}
