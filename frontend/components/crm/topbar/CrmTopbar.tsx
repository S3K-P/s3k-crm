'use client';

import { useState, useEffect } from 'react';
import { Search, Bell, Menu } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import AccountMenu from '@/components/crm/topbar/AccountMenu';
import CommandPalette from '@/components/crm/topbar/CommandPalette';
import AppLauncher from '@/components/platform/AppLauncher';
import { CRM_PRODUCT_CODE } from '@/features/platform/constants';
import { useSidebar } from '@/components/crm/sidebar/SidebarContext';

/* ============================================================
   CRM TOPBAR
   Horizontal top bar for the (crm) layout.

   The ⌘K palette lives in its own file (`CommandPalette`) since
   `P3-W20-FE-01`: it searches real records through `/crm/search`
   rather than the list of page names it used to filter, which is
   too much behaviour to keep inline in the chrome that opens it.
   ============================================================ */

export default function CrmTopbar() {
  const [searchOpen, setSearchOpen] = useState(false);
  const { setMobileOpen } = useSidebar();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <>
      {searchOpen && <CommandPalette onClose={() => setSearchOpen(false)} />}

      <div className="surface bd flex h-[60px] shrink-0 items-center gap-4 border-b px-5">
        {/* Mobile menu trigger */}
        <button
          className="md:hidden ctl txt-muted grid h-9 w-9 shrink-0 place-items-center rounded-[10px] transition hover:opacity-80"
          onClick={() => setMobileOpen(true)}
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* S3K app launcher — the CRM is one app on the platform, so the way
            out of it belongs in the chrome that is always present. Hidden on
            the narrowest screens, where the sidebar's own header carries the
            brand and space is scarce. */}
        <div className="hidden shrink-0 sm:block">
          <AppLauncher currentAppCode={CRM_PRODUCT_CODE} />
        </div>

        {/* Search trigger */}
        <button
          onClick={() => setSearchOpen(true)}
          className="ctl txt-faint flex w-[240px] flex-1 md:flex-none items-center gap-2 px-3.5 py-2 text-[13px] transition hover:opacity-80"
        >
          <Search className="h-4 w-4 shrink-0" />
          <span className="flex-1 text-left">Search…</span>
          <span className="bd rounded border px-1.5 py-0.5 text-[10px] font-semibold hidden md:block">⌘K</span>
        </button>

        {/* Right cluster */}
        <div className="ml-auto flex items-center gap-2.5">
          <ThemeToggle />

          <button className="ctl txt-muted grid h-9 w-9 place-items-center rounded-[10px] transition hover:opacity-80">
            <Bell className="h-[17px] w-[17px]" />
          </button>

          <AccountMenu />
        </div>
      </div>
    </>
  );
}
