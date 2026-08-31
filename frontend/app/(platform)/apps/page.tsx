'use client';

import Link from 'next/link';
import { AlertCircle, ArrowLeft, ArrowRight, Loader2 } from 'lucide-react';

import { AppIcon } from '@/features/platform/AppIcon';
import { usePlatformApps } from '@/features/platform/usePlatformApps';
import { APP_STATE_LABEL, type PlatformApp } from '@/features/platform/types';
import { useAuth } from '@/context/AuthContext';

/* ============================================================
   EXPLORE S3K APPS

   The S3K catalogue — first-party apps only, not a third-party
   marketplace. Every entry is a real row in `platform.products`,
   so this page cannot advertise something the backend has never
   heard of.

   The honesty rule this page exists to keep: an app that has not
   been built says "Coming soon" and offers no action. There is
   no button here that pretends to activate something, because
   nothing on the server would honour it.
   ============================================================ */

export default function ExploreAppsPage() {
  const { apps, loading, error } = usePlatformApps();
  const { can } = useAuth();

  // Administrators get pointed at the screen that can actually change this.
  const isAdmin = can('organizations', 'EDIT');

  return (
    <div className="mx-auto w-full max-w-[1100px] px-5 py-10 sm:px-8 sm:py-12">
      <Link
        href="/workspace"
        className="txt-muted inline-flex items-center gap-1.5 text-[12.5px] font-medium transition hover:opacity-80"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Workspace
      </Link>

      <header className="mt-4">
        <h1 className="font-display txt text-[26px] font-extrabold tracking-tight">
          Explore S3K
        </h1>
        <p className="txt-muted mt-1.5 max-w-[38rem] text-[13.5px] leading-relaxed">
          One S3K account, one organization, one sign-in — every app below shares
          the same users, roles and data boundaries.
        </p>
      </header>

      {loading && (
        <p className="txt-muted mt-8 flex items-center gap-2 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          Loading the S3K catalogue…
        </p>
      )}

      {error && !loading && (
        <p
          role="alert"
          className="mt-8 flex items-center gap-2 text-[13px] font-medium text-red-500"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}

      {!loading && !error && (
        <div className="mt-7 grid gap-4 sm:grid-cols-2">
          {apps.map((app) => (
            <CatalogueCard key={app.code} app={app} isAdmin={isAdmin} />
          ))}
        </div>
      )}

      {isAdmin && !loading && (
        <p className="txt-muted mt-8 text-[12.5px]">
          Switch apps on or off for your organization in{' '}
          <Link
            href="/admin/applications"
            className="font-semibold transition hover:opacity-80"
            style={{ color: 'var(--accent)' }}
          >
            Settings → Applications
          </Link>
          .
        </p>
      )}
    </div>
  );
}

function CatalogueCard({ app, isAdmin }: { app: PlatformApp; isAdmin: boolean }) {
  const openable = app.state === 'OPEN';

  return (
    <div
      className={`surface bd flex flex-col rounded-2xl border p-6 ${
        openable ? '' : 'opacity-[0.9]'
      }`}
    >
      <div className="flex items-start gap-3.5">
        <span
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl"
          style={{ background: openable ? 'var(--accent-soft)' : 'var(--surface-2)' }}
        >
          <AppIcon
            name={app.icon}
            className={`h-5 w-5 ${openable ? 'accent' : 'txt-faint'}`}
          />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display txt text-[15.5px] font-bold">{app.name}</h2>
            <span
              className="status-badge shrink-0 text-[10px] font-bold uppercase tracking-wider"
              style={openable ? { color: 'var(--accent)' } : undefined}
            >
              {APP_STATE_LABEL[app.state]}
            </span>
          </div>
          <p className="txt-muted mt-0.5 text-[12.5px] font-medium">{app.summary}</p>
        </div>
      </div>

      <p className="txt-muted mt-3.5 flex-1 text-[13px] leading-relaxed">{app.description}</p>

      <div className="mt-5">
        {app.state === 'OPEN' && (
          <Link
            href={app.route ?? '/workspace'}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            Open
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        )}

        {app.state === 'DISABLED' && (
          <p className="txt-muted text-[12.5px]">
            {isAdmin
              ? 'Your organization is licensed for this app but it is switched off.'
              : 'Switched off for your organization. Ask an administrator to turn it on.'}
          </p>
        )}

        {app.state === 'NOT_LICENSED' && (
          <p className="txt-muted text-[12.5px]">
            Not activated for your organization. Contact S3K to add it to your plan.
          </p>
        )}

        {app.state === 'COMING_SOON' && (
          <p className="txt-faint text-[12.5px]">In development — not yet available.</p>
        )}
      </div>
    </div>
  );
}
