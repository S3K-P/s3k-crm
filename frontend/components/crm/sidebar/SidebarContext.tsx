'use client';

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { createClientStore, useClientStore } from '@/lib/client-store';

interface SidebarCtx {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (v: boolean) => void;
  mobileOpen: boolean;
  setMobileOpen: (v: boolean) => void;
}

const SidebarContext = createContext<SidebarCtx | null>(null);

const STORAGE_KEY = 'crm-sidebar-collapsed';

/**
 * The collapsed state belongs to the browser, not to a React tree: it must
 * survive navigation and reloads, and it is read from `localStorage`, which
 * does not exist during SSR. Hydrating it from an effect would expand the
 * sidebar on every page load and then snap it shut.
 *
 * `mobileOpen` is deliberately *not* here — it is ordinary ephemeral UI state
 * that should reset on navigation, and persisting it would leave the drawer
 * open on the next visit.
 */
const collapsedStore = createClientStore<boolean>(
  () => localStorage.getItem(STORAGE_KEY) === 'true',
  (next) => localStorage.setItem(STORAGE_KEY, String(next)),
  false,
);

export function SidebarProvider({ children }: { children: ReactNode }) {
  const collapsed = useClientStore(collapsedStore);
  const [mobileOpen, setMobileOpen] = useState(false);

  const setCollapsed = useCallback((v: boolean) => collapsedStore.set(v), []);
  const toggle = useCallback(() => collapsedStore.set(!collapsedStore.get()), []);

  const value = useMemo(
    () => ({ collapsed, toggle, setCollapsed, mobileOpen, setMobileOpen }),
    [collapsed, toggle, setCollapsed, mobileOpen],
  );

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

export function useSidebar(): SidebarCtx {
  const ctx = useContext(SidebarContext);
  if (!ctx) {
    return { collapsed: false, toggle: () => {}, setCollapsed: () => {}, mobileOpen: false, setMobileOpen: () => {} };
  }
  return ctx;
}
