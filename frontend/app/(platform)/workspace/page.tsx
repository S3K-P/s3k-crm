'use client';

import Link from 'next/link';
import { AlertCircle, ArrowRight, Building2, Loader2, Users2 } from 'lucide-react';

import { AppIcon } from '@/features/platform/AppIcon';
import { usePlatformApps } from '@/features/platform/usePlatformApps';
import {
  APP_STATE_LABEL,
  exploreApps,
  openableApps,
  type PlatformApp,
} from '@/features/platform/types';
import { useAuth } from '@/context/AuthContext';

/* ============================================================
   S3K WORKSPACE

   The landing surface after sign-in, and deliberately *not* the
   CRM dashboard: this layer is about which app to open, so it
   shows no business metrics at all. Inventing a few would mean
   either querying every app for numbers the workspace has no
   opinion about, or displaying figures that are not real — and
   the latter is the thing this platform work is explicitly not
   allowed to do.
   ============================================================ */

/** Time-of-day greeting, from the viewer's own clock. */
function greeting(now: Date): string {
  const hour = now.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function WorkspacePage() {
  const { currentUser, memberships, activeOrganizationId } = useAuth();
  const { apps, loading, error } = usePlatformApps();

  const firstName = currentUser?.user.profile?.first_name?.trim();
  const organization = memberships.find(
    (membership) => membership.organization_id === activeOrganizationId,
  );

  const mine = openableApps(apps);
  const explore = exploreApps(apps);

  return (
    <div className="mx-auto w-full max-w-[1100px] px-5 py-10 sm:px-8 sm:py-12">
      {/* ── Greeting ── */}
      <header className="anim-fade-up">
        <h1 className="font-display txt text-[26px] font-extrabold tracking-tight sm:text-[30px]">
          {greeting(new Date())}
          {firstName ? `, ${firstName}` : ''}
        </h1>
        {organization && (
          <p className="txt-muted mt-1.5 flex items-center gap-1.5 text-[13.5px]">
            <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
            {organization.organization_name}
            <span className="txt-faint">·</span>
            <span className="txt-faint">{organization.roles.join(', ') || 'Member'}</span>
          </p>
        )}
      </header>

      {/* ── Your apps ── */}
      <section className="mt-9" aria-labelledby="your-apps">
        <h2
          id="your-apps"
          className="txt-faint text-[10.5px] font-bold uppercase tracking-[0.16em]"
        >
          Your apps
        </h2>

        {loading && (
          <p className="txt-muted mt-4 flex items-center gap-2 text-[13px]">
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
            Loading your apps…
          </p>
        )}

        {error && !loading && (
          <p
            role="alert"
            className="mt-4 flex items-center gap-2 text-[13px] font-medium text-red-500"
          >
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        {!loading && !error && mine.length === 0 && (
          <div className="surface bd mt-4 rounded-2xl border p-8 text-center">
            <Users2 className="txt-faint mx-auto h-7 w-7" aria-hidden="true" />
            <p className="txt mt-3 text-[14px] font-semibold">No apps are active yet</p>
            <p className="txt-muted mx-auto mt-1.5 max-w-[26rem] text-[13px]">
              Your organization has no S3K app switched on. An administrator can
              activate one from Settings, or browse what S3K offers.
            </p>
            <Link
              href="/apps"
              className="mt-5 inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              Explore S3K apps
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </div>
        )}

        {!loading && mine.length > 0 && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {mine.map((app) => (
              <OpenAppCard key={app.code} app={app} />
            ))}
          </div>
        )}
      </section>

      {/* ── Explore ── */}
      {!loading && explore.length > 0 && (
        <section className="mt-10" aria-labelledby="explore-s3k">
          <div className="flex items-baseline justify-between gap-4">
            <h2
              id="explore-s3k"
              className="txt-faint text-[10.5px] font-bold uppercase tracking-[0.16em]"
            >
              Explore S3K
            </h2>
            <Link
              href="/apps"
              className="text-[12.5px] font-semibold transition hover:opacity-80"
              style={{ color: 'var(--accent)' }}
            >
              View all
            </Link>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {explore.map((app) => (
              <ExploreAppCard key={app.code} app={app} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

/** An app the organization can open right now. The whole card is the link. */
function OpenAppCard({ app }: { app: PlatformApp }) {
  return (
    <Link
      href={app.route ?? '/workspace'}
      className="surface bd group flex flex-col rounded-2xl border p-5 transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-card)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
    >
      <span
        className="grid h-10 w-10 place-items-center rounded-xl"
        style={{ background: 'var(--accent-soft)' }}
      >
        <AppIcon name={app.icon} className="h-5 w-5 accent" />
      </span>
      <h3 className="font-display txt mt-3.5 text-[15px] font-bold">{app.name}</h3>
      <p className="txt-muted mt-1 flex-1 text-[12.5px] leading-relaxed">{app.summary}</p>
      <span
        className="mt-4 inline-flex items-center gap-1.5 text-[12.5px] font-semibold"
        style={{ color: 'var(--accent)' }}
      >
        Open app
        <ArrowRight
          className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </span>
    </Link>
  );
}

/**
 * An app that is not openable.
 *
 * Not a link, and it carries no call to action that would do nothing — the
 * status *is* the information. Turning these into buttons that open a "request
 * access" flow nobody has built would be the dead navigation this work is
 * meant to avoid.
 */
function ExploreAppCard({ app }: { app: PlatformApp }) {
  return (
    <div className="surface bd rounded-2xl border p-5 opacity-[0.86]">
      <span className="surface-2 grid h-10 w-10 place-items-center rounded-xl">
        <AppIcon name={app.icon} className="txt-faint h-5 w-5" />
      </span>
      <div className="mt-3.5 flex items-center gap-2">
        <h3 className="font-display txt text-[15px] font-bold">{app.name}</h3>
        <span className="status-badge txt-faint shrink-0 text-[10px] font-bold uppercase tracking-wider">
          {APP_STATE_LABEL[app.state]}
        </span>
      </div>
      <p className="txt-muted mt-1 text-[12.5px] leading-relaxed">{app.summary}</p>
    </div>
  );
}
