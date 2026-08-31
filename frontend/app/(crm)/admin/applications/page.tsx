'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertCircle, Loader2 } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import { AppIcon } from '@/features/platform/AppIcon';
import { usePlatformApps } from '@/features/platform/usePlatformApps';
import { APP_STATE_LABEL, type PlatformApp } from '@/features/platform/types';
import { usePermissions } from '@/context/AuthContext';
import { api, ApiError } from '@/lib/api-client';

/* ============================================================
   ADMIN → ORGANIZATION → APPLICATIONS

   Which S3K apps this organization has, and the switch for the
   ones it holds.

   **What this screen cannot do, by design.** It cannot grant an
   app. The toggle only narrows or restores a licence the
   organization already has, because an endpoint that granted
   entitlements would let an administrator license their own
   tenant (ADR-011). An unlicensed app therefore shows its state
   and a note about who to talk to, not a button that would 404.

   Turning an app off is a real control, not a UI preference: the
   backend's product gate refuses every API call for a disabled
   app with 403 `product_not_licensed`, so hiding the navigation
   is a consequence of the block rather than a substitute for it.
   ============================================================ */

export default function AdminApplicationsPage() {
  const { can } = usePermissions();
  const mayManage = can('organizations', 'EDIT');
  const { apps, loading, error, refresh } = usePlatformApps();

  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const toggle = async (app: PlatformApp) => {
    if (pending) return;
    setPending(app.code);
    setActionError(null);
    try {
      await api.put(`/products/apps/${encodeURIComponent(app.code)}/enablement`, {
        enabled: !app.enabled,
      });
      // Re-read rather than patching local state: the server owns the verdict,
      // and a licence that expired since the page loaded must not be shown as
      // "Active" merely because the toggle succeeded.
      await refresh();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to change that application right now.',
      );
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="font-display txt text-[22px] font-extrabold tracking-tight">
          Applications
        </h1>
        <p className="txt-muted mt-1 text-[13px]">
          S3K apps available to your organization. Turning one off blocks it for
          every member, in the interface and in the API.
        </p>
      </div>

      {!mayManage && (
        <p className="txt-muted mb-5 text-[12.5px]">
          You can see which applications your organization has, but only an
          administrator can turn them on or off.
        </p>
      )}

      {actionError && (
        <p
          role="alert"
          className="mb-4 flex items-center gap-2 text-[13px] font-medium text-red-500"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {actionError}
        </p>
      )}

      <SectionHeader
        title="Your organization"
        action={
          <Link
            href="/apps"
            className="text-[12.5px] font-semibold transition hover:opacity-80"
            style={{ color: 'var(--accent)' }}
          >
            Explore S3K apps
          </Link>
        }
      />

      {loading && (
        <p className="txt-muted flex items-center gap-2 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          Loading applications…
        </p>
      )}

      {error && !loading && (
        <p role="alert" className="text-[13px] font-medium text-red-500">
          {error}
        </p>
      )}

      {!loading && !error && (
        <ul className="space-y-2.5">
          {apps.map((app) => (
            <li
              key={app.code}
              className="surface bd flex flex-wrap items-center gap-4 rounded-xl border p-4"
            >
              <span
                className="grid h-10 w-10 shrink-0 place-items-center rounded-lg"
                style={{
                  background: app.entitled ? 'var(--accent-soft)' : 'var(--surface-2)',
                }}
              >
                <AppIcon
                  name={app.icon}
                  className={`h-5 w-5 ${app.entitled ? 'accent' : 'txt-faint'}`}
                />
              </span>

              <div className="min-w-[12rem] flex-1">
                <p className="txt text-[13.5px] font-semibold">{app.name}</p>
                <p className="txt-muted text-[12px]">{app.summary}</p>
              </div>

              <span
                className="status-badge shrink-0 text-[10.5px] font-bold uppercase tracking-wider"
                style={app.state === 'OPEN' ? { color: 'var(--accent)' } : undefined}
              >
                {APP_STATE_LABEL[app.state]}
              </span>

              <div className="shrink-0">
                {app.entitled && mayManage ? (
                  <button
                    type="button"
                    onClick={() => void toggle(app)}
                    disabled={pending !== null}
                    aria-pressed={app.enabled}
                    className="bd txt flex min-w-[6.5rem] items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {pending === app.code && (
                      <Loader2
                        className="h-3.5 w-3.5 motion-safe:animate-spin"
                        aria-hidden="true"
                      />
                    )}
                    {app.enabled ? 'Turn off' : 'Turn on'}
                  </button>
                ) : (
                  <span className="txt-faint block min-w-[6.5rem] text-right text-[12px]">
                    {app.availability === 'COMING_SOON'
                      ? 'In development'
                      : app.entitled
                        ? 'Admin only'
                        : 'Contact S3K'}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
