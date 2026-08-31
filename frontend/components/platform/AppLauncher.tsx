'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, Grid2x2, Loader2, LayoutGrid } from 'lucide-react';

import { AppIcon } from '@/features/platform/AppIcon';
import { usePlatformApps } from '@/features/platform/usePlatformApps';
import {
  APP_STATE_LABEL,
  exploreApps,
  openableApps,
} from '@/features/platform/types';

/* ============================================================
   S3K APP LAUNCHER

   The one control that makes this a platform rather than a set
   of separate products: switch apps without signing in again.

   Two sections, and the split is the server's verdict rather
   than ours — "Your Apps" is everything `state === 'OPEN'`,
   "Explore" is everything else. An app the organization is not
   licensed for is still *listed*, because a user who cannot see
   that HR exists cannot ask for it; it simply is not a link.
   ============================================================ */

export default function AppLauncher({ currentAppCode }: { currentAppCode?: string }) {
  const { apps, loading, error } = usePlatformApps();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close on outside click and on Escape. Escape also returns focus to the
  // trigger, so a keyboard user is not dropped at the top of the document.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      buttonRef.current?.focus();
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const mine = openableApps(apps);
  const explore = exploreApps(apps);
  const current = currentAppCode
    ? apps.find((app) => app.code === currentAppCode)
    : undefined;

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Switch S3K app"
        className="bd txt flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[13px] font-semibold transition-colors hover:bg-[var(--accent-soft)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
      >
        <Grid2x2 className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="max-w-[10rem] truncate">
          {current ? current.name.replace(/^S3K\s+/, '') : 'Workspace'}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="S3K apps"
          className="surface bd anim-tip-in absolute left-0 z-50 mt-2 w-[19rem] overflow-hidden rounded-xl border shadow-[var(--shadow-lift)]"
        >
          <div className="bd border-b px-3.5 py-2.5">
            <p className="txt-faint text-[10px] font-bold uppercase tracking-[0.14em]">
              S3K Apps
            </p>
          </div>

          {/* The way back up to the platform. Without it the launcher is a
              one-way door: from inside an app every entry leads to another
              app, and the workspace becomes unreachable without editing the
              URL. Hidden when the workspace is already what you are looking
              at, where it would be a link to the current page. */}
          {currentAppCode !== undefined && (
            <Link
              href="/workspace"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="txt bd flex items-center gap-2.5 border-b px-3.5 py-2.5 text-[13px] font-medium transition-colors hover:bg-[var(--accent-soft)] focus:outline-none focus-visible:bg-[var(--accent-soft)]"
            >
              <LayoutGrid className="txt-muted h-4 w-4" aria-hidden="true" />
              S3K Workspace
            </Link>
          )}

          {loading && (
            <p className="txt-muted flex items-center gap-2 px-3.5 py-4 text-[12.5px]">
              <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
              Loading your apps…
            </p>
          )}

          {error && !loading && (
            <p role="alert" className="px-3.5 py-4 text-[12.5px] font-medium text-red-500">
              {error}
            </p>
          )}

          {!loading && !error && (
            <div className="max-h-[22rem] overflow-y-auto py-1.5">
              <Section title="Your apps">
                {mine.length === 0 ? (
                  <p className="txt-faint px-3.5 py-2 text-[12.5px]">
                    No apps are active for this organization yet.
                  </p>
                ) : (
                  mine.map((app) => (
                    <Link
                      key={app.code}
                      href={app.route ?? '/workspace'}
                      role="menuitem"
                      onClick={() => setOpen(false)}
                      className="txt flex items-center gap-2.5 px-3.5 py-2 text-[13px] transition-colors hover:bg-[var(--accent-soft)] focus:outline-none focus-visible:bg-[var(--accent-soft)]"
                    >
                      <AppIcon name={app.icon} className="h-4 w-4 accent" />
                      <span className="flex-1 truncate font-medium">{app.name}</span>
                      {app.code === currentAppCode && (
                        <span
                          className="text-[10px] font-bold uppercase tracking-wider"
                          style={{ color: 'var(--accent)' }}
                        >
                          Current
                        </span>
                      )}
                    </Link>
                  ))
                )}
              </Section>

              {explore.length > 0 && (
                <Section title="Explore">
                  {explore.map((app) => (
                    <div
                      key={app.code}
                      className="flex items-center gap-2.5 px-3.5 py-2 text-[13px]"
                    >
                      <AppIcon name={app.icon} className="txt-faint h-4 w-4" />
                      <span className="txt-muted flex-1 truncate">{app.name}</span>
                      <span className="txt-faint text-[10.5px] font-semibold">
                        {APP_STATE_LABEL[app.state]}
                      </span>
                    </div>
                  ))}
                </Section>
              )}
            </div>
          )}

          <div className="bd border-t">
            <Link
              href="/apps"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3.5 py-2.5 text-[12.5px] font-semibold transition-colors hover:bg-[var(--accent-soft)] focus:outline-none focus-visible:bg-[var(--accent-soft)]"
              style={{ color: 'var(--accent)' }}
            >
              <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" />
              Explore all S3K apps
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="py-1">
      <p className="txt-faint px-3.5 pb-1 text-[10px] font-bold uppercase tracking-[0.14em]">
        {title}
      </p>
      {children}
    </div>
  );
}
