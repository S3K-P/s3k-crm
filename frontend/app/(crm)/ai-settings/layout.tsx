'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { 
  BrainCircuit, LayoutDashboard, Cpu, Bot, 
  MessageSquareCode, BookOpen, Zap, Layers, ShieldCheck
} from 'lucide-react';

const AI_NAVIGATION = [
  { group: 'Overview', items: [
    { name: 'Dashboard', href: '/ai-settings', icon: LayoutDashboard }
  ]},
  { group: 'Core Platform', items: [
    { name: 'Providers & Models', href: '/ai-settings/providers', icon: Cpu },
    { name: 'AI Copilot', href: '/ai-settings/copilot', icon: Bot },
    { name: 'AI Agents', href: '/ai-settings/agents', icon: BrainCircuit },
  ]},
  { group: 'Intelligence', items: [
    { name: 'Prompt Library', href: '/ai-settings/prompts', icon: MessageSquareCode },
    { name: 'Knowledge Base', href: '/ai-settings/knowledge', icon: BookOpen },
    { name: 'Automations', href: '/ai-settings/automations', icon: Zap },
  ]},
  { group: 'Domain AI', items: [
    { name: 'Features Configuration', href: '/ai-settings/features', icon: Layers },
  ]},
  { group: 'Governance', items: [
    { name: 'Security & Analytics', href: '/ai-settings/security-analytics', icon: ShieldCheck },
  ]}
];

export default function AISettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-full">
      
      {/* ── AI Settings Sidebar ── */}
      <aside className="w-64 flex-shrink-0 border-r border-[var(--border)] bg-[var(--surface-2)] overflow-y-auto hidden md:block">
        <div className="p-5 border-b border-[var(--border)] flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600">
            <BrainCircuit className="h-4 w-4 text-white" />
          </div>
          <div>
            <h2 className="font-display txt text-[16px] font-extrabold tracking-tight leading-tight">AI Control Center</h2>
            <p className="txt-muted text-[11px] font-medium">Enterprise Intelligence</p>
          </div>
        </div>
        
        <nav className="p-4 space-y-6">
          {AI_NAVIGATION.map((group, idx) => (
            <div key={idx}>
              <h3 className="px-2 txt-muted text-[10px] font-bold uppercase tracking-wider mb-2">{group.group}</h3>
              <ul className="space-y-0.5">
                {group.items.map(item => {
                  const isActive = pathname === item.href;
                  return (
                    <li key={item.name}>
                      <Link 
                        href={item.href}
                        className={cn(
                          "flex items-center gap-3 px-2 py-2 rounded-lg text-[13px] font-medium transition-colors",
                          isActive 
                            ? "bg-[var(--surface)] text-[var(--text)] shadow-sm border border-[var(--border)]" 
                            : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--surface)]/50"
                        )}
                      >
                        <item.icon className={cn("h-4 w-4", isActive ? "text-[var(--accent)]" : "")} />
                        {item.name}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      {/* ── AI Content Area ── */}
      <main className="flex-1 overflow-y-auto bg-[var(--bg)]">
        {children}
      </main>
      
    </div>
  );
}
