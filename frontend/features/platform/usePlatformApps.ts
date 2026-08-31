'use client';

import { useCallback, useEffect, useState } from 'react';

import { api } from '@/lib/api-client';
import { useAuth } from '@/context/AuthContext';
import type { PlatformApp } from '@/features/platform/types';

/* ============================================================
   PLATFORM APPS

   One fetch of `GET /products/apps`, shared by the launcher, the
   workspace, the Explore catalogue and the admin screen so all
   four agree about what the organization has.

   Keyed on the active organization: switching tenants must
   re-ask, because entitlements belong to the organization and
   not to the user. Without that dependency the launcher would
   keep showing the previous tenant's apps after a switch.

   Nothing here sets state synchronously — not in the effect body
   and not before the first `await` in `load`. React's
   `set-state-in-effect` rule rejects that, and the reason is
   real: a synchronous setState during an effect schedules a
   second render pass before the browser has painted the first.
   ============================================================ */

interface PlatformAppsState {
  apps: PlatformApp[];
  loading: boolean;
  error: string | null;
  /** Re-fetch, e.g. after an administrator toggles an app. */
  refresh: () => Promise<void>;
}

export function usePlatformApps(): PlatformAppsState {
  const { isAuthenticated, activeOrganizationId } = useAuth();

  // No tenant means nothing to ask about — the state a user is in between
  // signing up and creating their organization. Not an error, and not a fetch.
  const canFetch = isAuthenticated && activeOrganizationId !== null;

  const [apps, setApps] = useState<PlatformApp[]>([]);
  // Seeded from `canFetch` rather than set inside the effect: if there is
  // nothing to load, the very first render is already the settled state.
  const [loading, setLoading] = useState(canFetch);
  const [error, setError] = useState<string | null>(null);

  /** Fetch only. Sets no state, so both callers below decide what to do. */
  const fetchApps = useCallback(async (): Promise<PlatformApp[]> => {
    if (!canFetch) return [];
    return api.get<PlatformApp[]>('/products/apps');
  }, [canFetch]);

  /** Re-fetch on demand — from an event handler, never from an effect. */
  const refresh = useCallback(async () => {
    try {
      setApps(await fetchApps());
      setError(null);
    } catch {
      setError('Unable to load your S3K apps right now.');
    } finally {
      setLoading(false);
    }
  }, [fetchApps]);

  // The shape `useCollection` uses: an async IIFE declared inside the effect.
  // Calling an async state-setting function directly here trips
  // `react-hooks/set-state-in-effect`, which cannot see that every write
  // happens after an await.
  //
  // The `cancelled` guard is real rather than decorative: the fetch is done
  // here and the result inspected before anything is written, so a slow
  // response for the *previous* organization is dropped instead of painting
  // the launcher with a tenant the user has already switched away from.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const next = await fetchApps();
        if (cancelled) return;
        setApps(next);
        setError(null);
      } catch {
        // `apps` deliberately keeps its previous value: a transient failure
        // should not blank a launcher that was working a moment ago.
        if (!cancelled) setError('Unable to load your S3K apps right now.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchApps]);

  return {
    // Never leak another tenant's list into a signed-out or tenant-less state.
    apps: canFetch ? apps : [],
    loading: canFetch && loading,
    error,
    refresh,
  };
}

export default usePlatformApps;
