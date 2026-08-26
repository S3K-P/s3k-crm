'use client';

import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import { describeApiError } from '@/features/shared/hooks/useCollection';

/* ============================================================
   USE RECORD

   Loads one record by its route `[id]`, which is what every CRM
   detail page previously did not do — they rendered a hardcoded
   constant and ignored the URL entirely (risk R24).

   A 404 is modelled separately from a general error because it
   is not a failure: it means the id does not exist *in the
   caller's organization*, which is also exactly what another
   tenant's id looks like. The page says "not found" rather than
   "something went wrong".
   ============================================================ */

export type RecordStatus = 'loading' | 'ready' | 'missing' | 'error';

export interface RecordState<T> {
  status: RecordStatus;
  data: T | null;
  error: string | null;
  reload: () => void;
}

export function useRecord<T>(
  fetcher: (id: string) => Promise<T>,
  id: string | undefined,
  options: { errorMessage?: string } = {},
): RecordState<T> {
  const { loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();
  const { errorMessage = 'Could not load this record.' } = options;

  const [state, setState] = useState<{
    key: string;
    data: T | null;
    status: RecordStatus;
    error: string | null;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  const key = `${activeOrganizationId ?? 'none'}#${id ?? 'none'}#${attempt}`;

  useEffect(() => {
    if (authLoading || !isAuthenticated || !id) return;

    let cancelled = false;

    void (async () => {
      try {
        const data = await fetcher(id);
        if (!cancelled) setState({ key, data, status: 'ready', error: null });
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 404) {
          setState({ key, data: null, status: 'missing', error: null });
          return;
        }
        setState({
          key,
          data: null,
          status: 'error',
          error: describeApiError(caught, errorMessage),
        });
      }
    })();

    return () => {
      cancelled = true;
    };
    // `fetcher` is excluded deliberately — see useCollection for the reasoning.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, isAuthenticated, key, id]);

  const current = state?.key === key ? state : null;

  if (current === null) {
    return { status: 'loading', data: null, error: null, reload };
  }
  return {
    status: current.status,
    data: current.data,
    error: current.error,
    reload,
  };
}
