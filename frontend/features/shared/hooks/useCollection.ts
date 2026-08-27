'use client';

import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import type { Page, PageMeta } from '@/features/shared/types/api';

/* ============================================================
   USE COLLECTION

   One hook behind every CRM list screen. It exists so the
   dashboard's correctness properties are not re-implemented
   (and re-broken) on each page:

   - Results are stamped with the request they answered, so a
     slow response for the previous organization or filter set
     can never repaint the table with the wrong rows.
   - Changing organization invalidates everything by
     construction, because the organization id is part of the
     request key.
   - There is no fallback to sample data. A failure is reported
     as a failure; showing invented records under a real login
     would be worse than showing an error.
   ============================================================ */

export type CollectionStatus = 'loading' | 'ready' | 'error';

export interface CollectionState<T> {
  status: CollectionStatus;
  items: T[];
  pagination: PageMeta | null;
  error: string | null;
  /** Re-fetch the current page. Call after a create, edit or delete. */
  reload: () => void;
  /** True while a reload triggered by a mutation is in flight. */
  refreshing: boolean;
}

interface Result<T> {
  key: string;
  page: Page<T> | null;
  error: string | null;
}

export function describeApiError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return 'You do not have permission to do that.';
    return error.message;
  }
  if (error instanceof TypeError) {
    return 'Could not reach the API. Check that the backend is running.';
  }
  return fallback;
}

/**
 * Load one page of a collection.
 *
 * @param fetcher Must be stable across renders (wrap in `useCallback`), or
 *   memoised via `deps` — it is part of the request identity.
 * @param deps Values that should trigger a refetch when they change, such as
 *   the active search term or filter selection.
 */
export function useCollection<T>(
  fetcher: () => Promise<Page<T>>,
  deps: ReadonlyArray<unknown>,
  options: { errorMessage?: string } = {},
): CollectionState<T> {
  const { loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();
  const { errorMessage = 'Something went wrong loading this list.' } = options;

  const [result, setResult] = useState<Result<T> | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const reload = useCallback(() => {
    setRefreshing(true);
    setAttempt((n) => n + 1);
  }, []);

  // Identifies the data the screen should currently be showing. Anything that
  // changes what was asked for belongs in here.
  //
  // Computed on every render rather than memoised: `deps` is a fresh array each
  // time, so a dependency list built by spreading it is not a literal and
  // cannot be verified by the compiler. Serialising a handful of scalars is far
  // cheaper than the bookkeeping memoising it would need.
  const key = JSON.stringify([activeOrganizationId ?? 'none', attempt, ...deps]);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;

    let cancelled = false;

    void (async () => {
      try {
        const page = await fetcher();
        if (!cancelled) setResult({ key, page, error: null });
      } catch (caught) {
        if (!cancelled) {
          setResult({ key, page: null, error: describeApiError(caught, errorMessage) });
        }
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // `fetcher` is intentionally excluded: it is recreated on every render by
    // most callers, and `key` already captures everything that changes what it
    // would return.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, isAuthenticated, key]);

  const current = result?.key === key ? result : null;

  if (current === null) {
    return {
      status: 'loading',
      items: [],
      pagination: null,
      error: null,
      reload,
      refreshing,
    };
  }
  if (current.error !== null) {
    return {
      status: 'error',
      items: [],
      pagination: null,
      error: current.error,
      reload,
      refreshing,
    };
  }
  return {
    status: 'ready',
    items: current.page?.data ?? [],
    pagination: current.page?.pagination ?? null,
    error: null,
    reload,
    refreshing,
  };
}

/* ============================================================
   USE MUTATION
   Create / edit / delete, with the pending and error state the
   surrounding form needs to disable its submit button and say
   what went wrong.
   ============================================================ */

export interface MutationState {
  pending: boolean;
  error: string | null;
  clearError: () => void;
}

export function useMutation(): MutationState & {
  run: <T>(action: () => Promise<T>) => Promise<T | undefined>;
} {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    setPending(true);
    setError(null);
    try {
      return await action();
    } catch (caught) {
      setError(describeApiError(caught, 'The change could not be saved.'));
      return undefined;
    } finally {
      setPending(false);
    }
  }, []);

  return { pending, error, clearError, run };
}
