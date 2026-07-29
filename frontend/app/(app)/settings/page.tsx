'use client';

import { Settings, Moon, Sun } from 'lucide-react';
import Header from '@/components/Header';
import PageHeader from '@/components/PageHeader';
import { useTheme } from '@/context/ThemeContext';
import { cn } from '@/lib/utils';

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <>
      <Header />
      <PageHeader
        icon={Settings}
        title="Settings"
        subtitle="Sample settings page — theme preference persists in localStorage"
      />

      <div className="mx-auto max-w-2xl p-6">
        <div className="surface bd rounded-2xl border p-6">
          <h2 className="font-display txt text-lg font-bold">Appearance</h2>
          <p className="txt-muted mt-1 text-sm">Choose light or dark. The whole app follows the theme tokens.</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {([
              { id: 'light', label: 'Light', icon: Sun },
              { id: 'dark',  label: 'Dark',  icon: Moon },
            ] as const).map(opt => {
              const on = theme === opt.id;
              return (
                <button
                  key={opt.id}
                  onClick={() => setTheme(opt.id)}
                  className={cn('seg flex items-center justify-center gap-2 p-4 transition', on && 'seg-on')}
                >
                  <opt.icon className="h-4.5 w-4.5" style={{ color: on ? 'var(--accent)' : 'var(--muted)' }} />
                  <span className={cn('text-sm font-semibold', on ? 'accent' : 'txt-muted')}>{opt.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}
