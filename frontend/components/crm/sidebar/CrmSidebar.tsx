'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { PanelLeftClose, PanelLeft, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { BRAND } from '@/config/site';
import { CRM_NAV_SECTIONS } from '@/config/crm-navigation';
import { useSidebar } from '@/components/crm/sidebar/SidebarContext';
import BrandLogo from '@/components/brand/BrandLogo';
import { usePermissions } from '@/context/AuthContext';

/* ============================================================
   CRM SIDEBAR
   Persistent collapsible left sidebar for the (crm) layout.
   Uses the existing design-system tokens throughout.
   ============================================================ */

export default function CrmSidebar() {
  const pathname = usePathname();
  const { collapsed, toggle, mobileOpen, setMobileOpen } = useSidebar();
  const { can } = usePermissions();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + '/');

  // Entries the caller cannot view are hidden, and a section with nothing left
  // in it disappears rather than leaving an empty heading. This is presentation
  // only: the backend enforces the same permission on every request.
  const visibleSections = CRM_NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter(
      (item) => !item.permissionModule || can(item.permissionModule, 'VIEW'),
    ),
  })).filter((section) => section.items.length > 0);

  return (
    <>
      {/* Mobile overlay backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          'crm-sidebar bg-navy-900 bd flex h-full flex-col border-r transition-all duration-200 ease-in-out',
          // Desktop sizing
          'max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-50 max-md:w-[280px]',
          // Mobile state
          !mobileOpen && 'max-md:-translate-x-full',
          'md:relative md:translate-x-0',
          collapsed ? 'md:w-[68px]' : 'md:w-[252px]',
        )}
      >
        {/* ── Brand ── */}
        <div className={cn('flex h-[60px] shrink-0 items-center justify-between px-4', collapsed && 'md:justify-center md:px-0')}>
          <Link href={BRAND.homeHref} className="flex shrink-0 items-center gap-2.5" onClick={() => setMobileOpen(false)}>
            <BrandLogo variant="icon" priority />
            <div className={cn("leading-none", collapsed && "md:hidden")}>
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
          </Link>
          <button className="md:hidden p-1 txt-muted hover:txt" onClick={() => setMobileOpen(false)}>
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* ── Navigation ── */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2.5 pb-4">
          {visibleSections.map((section) => (
            <div key={section.title} className="mt-5 first:mt-2">
              <div className={cn(
                "txt-faint mb-1.5 px-2.5 text-[10.5px] font-bold uppercase tracking-wider",
                collapsed && "md:hidden"
              )}>
                {section.title}
              </div>
              <div className={cn("bd mx-auto mb-2 mt-1 w-6 border-t hidden", collapsed && "md:block")} />

              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const on = isActive(item.href);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.id}
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      title={collapsed ? item.label : undefined}
                      className={cn(
                        'group flex items-center gap-3 rounded-xl px-2.5 py-2 text-[13px] font-medium transition-colors',
                        collapsed && 'md:justify-center md:px-0',
                        on
                          ? 'font-semibold text-white'
                          : 'txt-muted hover:surface-2',
                      )}
                      style={on ? { background: 'var(--accent)' } : undefined}
                    >
                      <Icon
                        className={cn('h-[18px] w-[18px] shrink-0', !on && 'opacity-70')}
                      />
                      <span className={cn("truncate", collapsed && "md:hidden")}>{item.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* ── Collapse toggle ── */}
        <div className="bd shrink-0 border-t p-2.5 hidden md:block">
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
    </>
  );
}
