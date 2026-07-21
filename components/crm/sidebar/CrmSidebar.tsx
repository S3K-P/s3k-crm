'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { PanelLeftClose, PanelLeft } from 'lucide-react';
import { cn } from '@/lib/utils';
import { BRAND } from '@/config/site';
import { CRM_NAV_SECTIONS } from '@/config/crm-navigation';
import { useSidebar } from '@/components/crm/sidebar/SidebarContext';

/* ============================================================
   CRM SIDEBAR
   Persistent collapsible left sidebar for the (crm) layout.
   Uses the existing design-system tokens throughout.
   ============================================================ */

export default function CrmSidebar() {
  const pathname = usePathname();
  const { collapsed, toggle } = useSidebar();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + '/');

  return (
    <aside
      className={cn(
        'surface bd flex h-full flex-col border-r transition-[width] duration-200 ease-in-out',
        collapsed ? 'w-[68px]' : 'w-[252px]',
      )}
    >
      {/* ── Brand ── */}
      <div className={cn('flex h-[60px] shrink-0 items-center gap-2.5 px-4', collapsed && 'justify-center px-0')}>
        <Link href={BRAND.homeHref} className="flex shrink-0 items-center gap-2.5">
          <div className="font-display flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-500 text-[11px] font-extrabold tracking-tight text-white">
            {BRAND.mark}
          </div>
          {!collapsed && (
            <div className="leading-none">
              <div className="font-display txt text-[15px] font-extrabold tracking-[-0.02em]">
                {BRAND.name}
              </div>
              <div
                className="text-[8.5px] font-bold uppercase tracking-[0.16em]"
                style={{ color: 'var(--accent)' }}
              >
                {BRAND.tagline}
              </div>
            </div>
          )}
        </Link>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2.5 pb-4">
        {CRM_NAV_SECTIONS.map((section) => (
          <div key={section.title} className="mt-5 first:mt-2">
            {!collapsed && (
              <div className="txt-faint mb-1.5 px-2.5 text-[10.5px] font-bold uppercase tracking-wider">
                {section.title}
              </div>
            )}
            {collapsed && <div className="bd mx-auto mb-2 mt-1 w-6 border-t" />}

            <div className="space-y-0.5">
              {section.items.map((item) => {
                const on = isActive(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.id}
                    href={item.href}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      'group flex items-center gap-3 rounded-xl px-2.5 py-2 text-[13px] font-medium transition-colors',
                      collapsed && 'justify-center px-0',
                      on
                        ? 'font-semibold text-white'
                        : 'txt-muted hover:surface-2',
                    )}
                    style={on ? { background: 'var(--accent)' } : undefined}
                  >
                    <Icon
                      className={cn('h-[18px] w-[18px] shrink-0', !on && 'opacity-70')}
                    />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* ── Collapse toggle ── */}
      <div className="bd shrink-0 border-t p-2.5">
        <button
          onClick={toggle}
          className="ctl txt-muted flex w-full items-center justify-center gap-2 rounded-xl py-2 text-[12px] font-medium transition hover:opacity-80"
        >
          {collapsed
            ? <PanelLeft className="h-4 w-4" />
            : (
              <>
                <PanelLeftClose className="h-4 w-4" />
                <span>Collapse</span>
              </>
            )}
        </button>
      </div>
    </aside>
  );
}
