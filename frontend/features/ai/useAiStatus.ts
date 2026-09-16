'use client';

import { useCallback, useEffect, useSyncExternalStore } from 'react';

import { useAuth } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { getAiStatus, type AiStatus } from '@/features/ai/status';

/* ============================================================
   useAiStatus

   The one place the frontend learns the AI connection state.

   A module-level store rather than per-component state, so the
   sidebar-adjacent AI screens and anything they render share one
   answer and one request: navigating between AI pages within a
   minute reuses it instead of asking again.

   It only ever calls `GET /ai/status`, which never reaches a
   model. The real connection test (`POST /ai/health`) spends
   provider quota and runs only when an administrator presses
   the button on Providers & Models — never on page load.
   ============================================================ */

/** How long an answer is reused before the next screen asks again. */
const FRESH_FOR_MS = 60_000;

interface Snapshot {
  status: AiStatus | null;
  error: string | null;
  fetchedAt: number;
}

const EMPTY: Snapshot = { status: null, error: null, fetchedAt: 0 };

let snapshot: Snapshot = EMPTY;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function publish(next: Snapshot): void {
  snapshot = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Fetch the status unless a fresh answer is already held.
 *
 * `force` is for after something changed it — a connection test just ran —
 * when a minute-old answer is known to be stale.
 */
export function loadAiStatus(force = false): Promise<void> {
  if (inflight) return inflight;
  if (!force && snapshot.fetchedAt > 0 && Date.now() - snapshot.fetchedAt < FRESH_FOR_MS) {
    return Promise.resolve();
  }
  inflight = getAiStatus()
    .then((status) => publish({ status, error: null, fetchedAt: Date.now() }))
    .catch((caught: unknown) =>
      publish({
        // The last known answer is kept: a transient failure to *ask* is not
        // evidence that AI stopped working.
        status: snapshot.status,
        error: describeApiError(caught, 'Could not reach the AI service.'),
        fetchedAt: Date.now(),
      }),
    )
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export interface UseAiStatus {
  status: AiStatus | null;
  /** Set when the status itself could not be fetched. */
  error: string | null;
  /** True until the first answer (or failure) arrives. */
  loading: boolean;
  refresh: () => Promise<void>;
}

export function useAiStatus(): UseAiStatus {
  const { loading: authLoading, isAuthenticated } = useAuth();
  const current = useSyncExternalStore(
    subscribe,
    () => snapshot,
    () => EMPTY,
  );

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;
    void loadAiStatus();
  }, [authLoading, isAuthenticated]);

  const refresh = useCallback(() => loadAiStatus(true), []);

  return {
    status: current.status,
    error: current.error,
    loading: current.status === null && current.error === null,
    refresh,
  };
}
