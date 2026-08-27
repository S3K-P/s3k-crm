'use client';

import { Moon, Sun } from 'lucide-react';
import { useTheme } from '@/context/ThemeContext';
import { useHasHydrated } from '@/lib/client-store';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  // The stored theme is unknown during SSR, so the icon is neutral until the
  // client has hydrated. Asking the store rather than setting state in an
  // effect keeps this to a single render.
  const hydrated = useHasHydrated();

  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
      className="ctl txt-muted grid h-9 w-9 place-items-center rounded-[10px] transition hover:opacity-80"
    >
      {hydrated && theme === 'dark'
        ? <Sun className="h-[18px] w-[18px]" />
        : <Moon className="h-[18px] w-[18px]" />}
    </button>
  );
}
