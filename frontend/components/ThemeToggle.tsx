'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '@/context/ThemeContext';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Avoid hydration mismatch: render a neutral icon until mounted.
  useEffect(() => setMounted(true), []);

  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
      className="ctl txt-muted grid h-9 w-9 place-items-center rounded-[10px] transition hover:opacity-80"
    >
      {mounted && theme === 'dark'
        ? <Sun className="h-[18px] w-[18px]" />
        : <Moon className="h-[18px] w-[18px]" />}
    </button>
  );
}
