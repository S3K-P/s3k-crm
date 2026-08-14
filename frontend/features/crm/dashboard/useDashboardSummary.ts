'use client';

import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import { AUTH_ENABLED } from '@/lib/api-config';
import { fetchDashboardSummary } from '@/features/crm/dashboard/api';
import type { DashboardSummary } from '@/features/crm/dashboard/types';

/* ============================================================
   USE DASHBOARD SUMMARY

   Loads the real summary for the **active organization** and
   reloads when that organization changes.

   Each result is stamped with the request it answered. Anything
   that does not match the request the component is currently
   waiting for is ignored on arrival and treated as absent on
   render — so a slow response for the previous organization can
   never repaint the page with the wrong tenant's numbers, and a
   switch shows the loading state rather than stale figures.

   There is no demo fallback. If the request fails the hook
   reports the failure and the page says so; showing invented
   figures under a real user's login would be worse than showing
   nothing.
   ============================================================ */

export type DashboardStatus = 'disabled' | 'loading' | 'ready' | 'error';

export interface DashboardState {
  status: DashboardStatus;
  data: DashboardSummary | null;
  /** Human-readable failure, present only when `status === 'error'`. */
  error: string | null;
  reload: () => void;
}

interface Result {
  /** The request this answered. */
  key: string;
  data: DashboardSummary | null;
  error: string | null;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'You do not have permission to view the dashboard in this organization.';
    }
    return error.message;
  }
  if (error instanceof TypeError) {
    return 'Could not reach the API. Check that the backend is running.';
  }
  return 'Something went wrong loading the dashboard.';
}

export function useDashboardSummary(): DashboardState {
  const { loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();

  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // Identifies the data the page should currently be showing. Changing
  // organization — or asking for a retry — makes any older result stale by
  // construction, with no state to reset.
  const key = `${activeOrganizationId ?? 'none'}#${attempt}`;

  useEffect(() => {
    if (!AUTH_ENABLED || authLoading || !isAuthenticated) return;

    let cancelled = false;

    void (async () => {
      try {
        const summary = await fetchDashboardSummary();
        if (!cancelled) setResult({ key, data: summary, error: null });
      } catch (caught) {
        if (!cancelled) setResult({ key, data: null, error: describe(caught) });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated, key]);

  if (!AUTH_ENABLED) {
    return { status: 'disabled', data: null, error: null, reload };
  }

  const current = result?.key === key ? result : null;

  if (current === null) {
    return { status: 'loading', data: null, error: null, reload };
  }
  if (current.error !== null) {
    return { status: 'error', data: null, error: current.error, reload };
  }
  return { status: 'ready', data: current.data, error: null, reload };
}
