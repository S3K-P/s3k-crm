'use client';

import { createContext, useCallback, useContext, useMemo } from 'react';
import { createClientStore, useClientStore } from '@/lib/client-store';

type Theme = 'light' | 'dark';

interface ThemeCtx {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeCtx | null>(null);

const STORAGE_KEY = 'app-theme';

/** Inline script string — runs before paint to set the .dark class (no FOUC). */
export const themeInitScript = `
(function(){
  try {
    var t = localStorage.getItem('${STORAGE_KEY}');
    if (!t) { t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; }
    if (t === 'dark') document.documentElement.classList.add('dark');
  } catch (e) {}
})();
`;

/**
 * The `.dark` class on `<html>` is the theme's source of truth, not a mirror
 * of it: `themeInitScript` sets it before React exists, precisely so the first
 * paint is already correct. Reading it through a store keeps that authority
 * where it is — the alternative, seeding state to `'light'` and correcting it
 * from an effect, renders the wrong theme once on every mount.
 */
const themeStore = createClientStore<Theme>(
  () => (document.documentElement.classList.contains('dark') ? 'dark' : 'light'),
  (next) => {
    document.documentElement.classList.toggle('dark', next === 'dark');
    localStorage.setItem(STORAGE_KEY, next);
  },
  // SSR has no `<html>` to read and no stored preference; the init script
  // corrects the class before paint, and hydration agrees because the server
  // and the hydrating client both start here.
  'light',
);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useClientStore(themeStore);

  const setTheme = useCallback((t: Theme) => themeStore.set(t), []);
  const toggleTheme = useCallback(
    () => themeStore.set(themeStore.get() === 'dark' ? 'light' : 'dark'),
    [],
  );

  const value = useMemo(
    () => ({ theme, toggleTheme, setTheme }),
    [theme, toggleTheme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    // Safe fallback so a stray consumer never crashes the page. It drives the
    // same store, so a toggle from outside the provider still works and stays
    // consistent with everything inside it.
    return {
      theme: 'light',
      toggleTheme: () => themeStore.set(themeStore.get() === 'dark' ? 'light' : 'dark'),
      setTheme: (t: Theme) => themeStore.set(t),
    };
  }
  return ctx;
}
