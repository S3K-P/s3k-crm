'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Search, Bell, X, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import ThemeToggle from '@/components/ThemeToggle';
import BrandLogo from '@/components/brand/BrandLogo';
import { BRAND, TABS, SUBNAV, SEARCH_ITEMS, type TabId } from '@/config/site';

/* ============================================================
   TOP-TAB NAVIGATION SHELL
   All brand / tab / sub-nav data comes from config/site.ts —
   edit that file for your project, not this component.
   ============================================================ */

function activeTab(pathname: string): TabId {
  for (const tab of TABS) {
    if (tab.match.some(m => pathname === m || pathname.startsWith(m + '/') || pathname.startsWith(m))) {
      return tab.id;
    }
  }
  return TABS[0].id;
}

interface HeaderProps {
  /** Optional page-level action rendered in the top bar */
  action?: React.ReactNode;
}

function SearchModal({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('');
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const results = query.trim().length === 0
    ? SEARCH_ITEMS
    : SEARCH_ITEMS.filter(item =>
        item.label.toLowerCase().includes(query.toLowerCase()) ||
        item.group.toLowerCase().includes(query.toLowerCase())
      );

  const grouped = results.reduce<Record<string, typeof SEARCH_ITEMS>>((acc, item) => {
    (acc[item.group] ||= []).push(item);
    return acc;
  }, {});

  const handleSelect = (href: string) => { router.push(href); onClose(); };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="surface bd fixed left-1/2 top-[12%] z-50 w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-2xl border shadow-[0_32px_80px_-20px_rgba(0,0,0,0.4)]">
        <div className="bd flex items-center gap-3 border-b px-4 py-3.5">
          <Search className="h-5 w-5 shrink-0" style={{ color: 'var(--accent)' }} />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search pages…"
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
          {Object.keys(grouped).length === 0 ? (
            <div className="txt-faint py-10 text-center text-sm">No results for &ldquo;{query}&rdquo;</div>
          ) : (
            Object.entries(grouped).map(([group, items]) => (
              <div key={group} className="mb-2">
                <div className="txt-faint px-3 pb-1 pt-2 text-[10.5px] font-bold uppercase tracking-wider">{group}</div>
                {items.map(item => (
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
                ))}
              </div>
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

export default function Header({ action }: HeaderProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const pathname = usePathname();
  const current = activeTab(pathname);
  const subItems = SUBNAV[current];

  const isSubActive = (href: string) => pathname === href || pathname.startsWith(href + '/');

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
      {searchOpen && <SearchModal onClose={() => setSearchOpen(false)} />}

      <div className="surface bd sticky top-0 z-20 border-b">
        {/* ── Row 1: brand · tabs · search · theme · bell · avatar ── */}
        <div className="flex h-[60px] items-center gap-4 px-5">
          {/* Brand */}
          <Link href={BRAND.homeHref} className="bd flex shrink-0 items-center gap-2.5 border-r pr-4">
            <BrandLogo priority />
            <div className="leading-none">
              <div className="font-display txt text-[15px] font-extrabold tracking-[-0.02em]">{BRAND.name}</div>
              <div className="text-[8.5px] font-bold uppercase tracking-[0.16em]" style={{ color: 'var(--accent)' }}>
                {BRAND.tagline}
              </div>
            </div>
          </Link>

          {/* Top tabs */}
          <nav className="flex items-center gap-1">
            {TABS.map(tab => {
              const on = tab.id === current;
              const Icon = tab.icon;
              const href = SUBNAV[tab.id][0]?.href ?? BRAND.homeHref;
              return (
                <Link
                  key={tab.id}
                  href={href}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-3.5 py-2 text-[13.5px] font-semibold transition-colors',
                    on ? 'text-white' : 'txt-muted hover:opacity-80',
                  )}
                  style={on ? { background: 'var(--accent)' } : undefined}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </Link>
              );
            })}
          </nav>

          {/* Page-level action slot */}
          {action && <div className="min-w-0">{action}</div>}

          <div className="ml-auto flex items-center gap-2.5">
            <button
              onClick={() => setSearchOpen(true)}
              className="ctl txt-faint flex w-[210px] items-center gap-2 px-3.5 py-2 text-[13px] transition hover:opacity-80"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="flex-1 text-left">Search…</span>
              <span className="bd rounded border px-1.5 py-0.5 text-[10px] font-semibold">⌘K</span>
            </button>

            <ThemeToggle />

            <button className="ctl txt-muted grid h-9 w-9 place-items-center rounded-[10px] transition hover:opacity-80">
              <Bell className="h-[17px] w-[17px]" />
            </button>

            <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-[12px] font-bold text-white">
              U
            </div>
          </div>
        </div>

        {/* ── Row 2: contextual sub-nav for the active tab ── */}
        {subItems.length > 1 && (
          <div className="surface-2 bd flex h-[44px] items-center gap-1.5 overflow-x-auto border-t px-5">
            {subItems.map(item => {
              const on = isSubActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'whitespace-nowrap rounded-lg px-3 py-1.5 text-[12.5px] transition-colors',
                    on ? 'surface bd border font-semibold' : 'txt-muted font-medium hover:opacity-80',
                  )}
                  style={on ? { color: 'var(--accent)' } : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
