'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { 
  LayoutDashboard, Users, Shield, UsersRound, Settings,
  Workflow, Database, Bell, Blocks, ScrollText, Lock, Grid2x2, MailPlus
} from 'lucide-react';

const ADMIN_NAVIGATION = [
  { group: 'Overview', items: [
    { name: 'Dashboard', href: '/admin', icon: LayoutDashboard }
  ]},
  { group: 'Organization', items: [
    { name: 'Applications', href: '/admin/applications', icon: Grid2x2 },
  ]},
  { group: 'Access Management', items: [
    { name: 'Users', href: '/admin/users', icon: Users },
    { name: 'Invitations', href: '/admin/invitations', icon: MailPlus },
    { name: 'Roles & Permissions', href: '/admin/roles', icon: Shield },
    { name: 'Teams', href: '/admin/teams', icon: UsersRound },
  ]},
  { group: 'System Configuration', items: [
    { name: 'CRM Settings', href: '/admin/crm-settings', icon: Settings },
    { name: 'Workflows', href: '/admin/workflows', icon: Workflow, disabled: true },
    { name: 'Data Management', href: '/admin/data', icon: Database, disabled: true },
    { name: 'Notifications', href: '/admin/notifications', icon: Bell, disabled: true },
  ]},
  { group: 'Extensions', items: [
    { name: 'Integrations', href: '/admin/integrations', icon: Blocks },
  ]},
  { group: 'Security & Compliance', items: [
    { name: 'Audit Logs', href: '/admin/audit-logs', icon: ScrollText },
    { name: 'Security & Billing', href: '/admin/security', icon: Lock },
  ]}
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-full">
      
      {/* ── Admin Sidebar ── */}
      <aside className="w-64 flex-shrink-0 border-r border-[var(--border)] bg-[var(--surface-2)] overflow-y-auto hidden md:block">
        <div className="p-5 border-b border-[var(--border)]">
          <h2 className="font-display txt text-[18px] font-extrabold tracking-tight">Admin Console</h2>
          <p className="txt-muted text-[12px] mt-0.5">Enterprise Configuration</p>
        </div>
        
        <nav className="p-4 space-y-6">
          {ADMIN_NAVIGATION.map((group, idx) => (
            <div key={idx}>
              <h3 className="px-2 txt-muted text-[10px] font-bold uppercase tracking-wider mb-2">{group.group}</h3>
              <ul className="space-y-0.5">
                {group.items.map(item => {
                  const isActive = pathname === item.href;
                  return (
                    <li key={item.name}>
                      {item.disabled ? (
                        <div className="flex items-center gap-3 px-2 py-2 rounded-lg text-[13px] font-medium text-[var(--muted)] opacity-60 cursor-not-allowed">
                          <item.icon className="h-4 w-4" />
                          {item.name}
                        </div>
                      ) : (
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
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      {/* ── Admin Content Area ── */}
      <main className="flex-1 overflow-y-auto bg-[var(--bg)]">
        {children}
      </main>
      
    </div>
  );
}
