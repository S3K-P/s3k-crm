'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Bell, X, ArrowRight } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import { CRM_NAV_ITEMS } from '@/config/crm-navigation';
import { useSidebar } from '@/components/crm/sidebar/SidebarContext';

/* ============================================================
   CRM TOPBAR
   Horizontal top bar for the (crm) layout.
   Reuses the same search, bell, and avatar patterns from the
   existing Header component, styled with existing tokens.
   ============================================================ */

function CrmSearchModal({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('');
  const router = useRouter();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const results = query.trim().length === 0
    ? CRM_NAV_ITEMS
    : CRM_NAV_ITEMS.filter(item =>
        item.label.toLowerCase().includes(query.toLowerCase())
      );

  const handleSelect = (href: string) => { router.push(href); onClose(); };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="surface bd fixed left-1/2 top-[12%] z-50 w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-2xl border shadow-[0_32px_80px_-20px_rgba(0,0,0,0.4)]">
        <div className="bd flex items-center gap-3 border-b px-4 py-3.5">
          <Search className="h-5 w-5 shrink-0" style={{ color: 'var(--accent)' }} />
          <input
            autoFocus
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search CRM pages…"
            className="txt flex-1 bg-transparent text-[15px] font-medium outline-none placeholder:opacity-50"
          />
          {query && (
            <button onClick={() => setQuery('')} className="txt-faint hover:opacity-70">
              <X className="h-4 w-4" />
            </button>
          )}
          <kbd className="bd txt-faint hidden rounded-md border px-1.5 py-0.5 text-[10.5px] font-semibold sm:block">ESC</kbd>
        </div>

        <div className="max-h-[420px] overflow-y-auto p-2">
          {results.length === 0 ? (
            <div className="txt-faint py-10 text-center text-sm">No results for &ldquo;{query}&rdquo;</div>
          ) : (
            results.map(item => (
              <button
                key={item.href}
                onClick={() => handleSelect(item.href)}
                className="hover:surface-2 flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition-colors"
              >
                <div className="surface-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px]">
                  <item.icon className="h-4 w-4" style={{ color: 'var(--accent)' }} />
                </div>
                <span className="txt flex-1 text-[13.5px] font-medium">{item.label}</span>
                <ArrowRight className="txt-faint h-3.5 w-3.5" />
              </button>
            ))
          )}
        </div>

        <div className="bd txt-faint flex items-center gap-4 border-t px-4 py-2.5 text-[11px]">
          <span><kbd className="bd rounded border px-1 py-0.5 font-semibold">↑↓</kbd> navigate</span>
          <span><kbd className="bd rounded border px-1 py-0.5 font-semibold">↵</kbd> open</span>
          <span><kbd className="bd rounded border px-1 py-0.5 font-semibold">ESC</kbd> close</span>
        </div>
      </div>
    </>
  );
}

export default function CrmTopbar() {
  const [searchOpen, setSearchOpen] = useState(false);
  const { collapsed } = useSidebar();

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
      {searchOpen && <CrmSearchModal onClose={() => setSearchOpen(false)} />}

      <div className="surface bd flex h-[60px] shrink-0 items-center gap-4 border-b px-5">
        {/* Search trigger */}
        <button
          onClick={() => setSearchOpen(true)}
          className="ctl txt-faint flex w-[240px] items-center gap-2 px-3.5 py-2 text-[13px] transition hover:opacity-80"
        >
          <Search className="h-4 w-4 shrink-0" />
          <span className="flex-1 text-left">Search…</span>
          <span className="bd rounded border px-1.5 py-0.5 text-[10px] font-semibold">⌘K</span>
        </button>

        {/* Right cluster */}
        <div className="ml-auto flex items-center gap-2.5">
          <ThemeToggle />

          <button className="ctl txt-muted grid h-9 w-9 place-items-center rounded-[10px] transition hover:opacity-80">
            <Bell className="h-[17px] w-[17px]" />
          </button>

          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-[12px] font-bold text-white">
            U
          </div>
        </div>
      </div>
    </>
  );
}
