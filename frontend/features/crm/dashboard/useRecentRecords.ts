'use client';

import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import { fetchRecentRecords } from '@/features/crm/dashboard/api';
import type { RecentRecordEntry } from '@/features/crm/dashboard/types';

export type RecentRecordsStatus = 'loading' | 'ready' | 'error';

export interface RecentRecordsState {
  status: RecentRecordsStatus;
  items: RecentRecordEntry[];
  error: string | null;
  fetchedAt: Date | null;
  reload: () => void;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Could not load recent records.';
}

interface Result {
  /** The request this answered: organization + retry attempt. */
  key: string;
  items: RecentRecordEntry[] | null;
  error: string | null;
}

export function useRecentRecords(): RecentRecordsState {
  const { loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();

  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  const key = `${activeOrganizationId ?? 'none'}#${attempt}`;

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;

    let cancelled = false;

    void (async () => {
      try {
        const items = await fetchRecentRecords();
        if (!cancelled) {
          setResult({ key, items, error: null });
          setFetchedAt(new Date());
        }
      } catch (caught) {
        if (!cancelled) setResult({ key, items: null, error: describe(caught) });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated, key]);

  const current = result?.key === key ? result : null;

  if (current === null) {
    return { status: 'loading', items: [], error: null, fetchedAt: null, reload };
  }
  if (current.error !== null) {
    return { status: 'error', items: [], error: current.error, fetchedAt: null, reload };
  }
  return { status: 'ready', items: current.items ?? [], error: null, fetchedAt, reload };
}
