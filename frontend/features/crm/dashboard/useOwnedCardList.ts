'use client';

import { useEffect, useRef, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import type { Page } from '@/features/shared/types/api';

/* ============================================================
   USE OWNED CARD LIST

   Shared data-fetching for the "My Leads" / "My Open Deals" /
   "My Contacts" dashboard cards: each is the same shape — the
   signed-in user's own rows from an existing list endpoint, with
   an inline search box.

   There is no demo fallback here either. A card that cannot reach
   the API reports that in its own small footprint rather than
   hiding the problem behind an empty state that looks like "you
   have no leads".
   ============================================================ */

export type CardListStatus = 'loading' | 'ready' | 'error';

export interface OwnedCardListState<T> {
  status: CardListStatus;
  items: T[];
  error: string | null;
  /** When this card's data last finished loading successfully. */
  fetchedAt: Date | null;
  search: string;
  setSearch: (value: string) => void;
  reload: () => void;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Could not load this list.';
}

const SEARCH_DEBOUNCE_MS = 300;

interface Result<T> {
  /** The request this answered: owner + search + retry attempt. */
  key: string;
  items: T[] | null;
  error: string | null;
}

export function useOwnedCardList<T>(
  fetcher: (params: { ownerId: string; search: string }) => Promise<Page<T>>,
): OwnedCardListState<T> {
  const { loading: authLoading, isAuthenticated, activeOrganizationId, currentUser } = useAuth();
  const ownerId = currentUser?.user.id ?? null;

  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // `fetcher` is a fresh closure every render (each card builds its own
  // request inline), so it cannot sit in the effect's dependency array
  // without re-running on every render. A ref holds "the latest fetcher" for
  // the effect to call, synced after render rather than during it.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const [result, setResult] = useState<Result<T> | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const key = `${ownerId ?? 'none'}#${activeOrganizationId ?? 'none'}#${debouncedSearch}#${attempt}`;

  useEffect(() => {
    if (authLoading || !isAuthenticated || !ownerId) return;

    let cancelled = false;

    void (async () => {
      try {
        const page = await fetcherRef.current({ ownerId, search: debouncedSearch });
        if (!cancelled) {
          setResult({ key, items: page.data, error: null });
          setFetchedAt(new Date());
        }
      } catch (caught) {
        if (!cancelled) setResult({ key, items: null, error: describe(caught) });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated, ownerId, key, debouncedSearch]);

  const current = result?.key === key ? result : null;
  const status: CardListStatus = current === null ? 'loading' : current.error ? 'error' : 'ready';

  return {
    status,
    items: current?.items ?? [],
    error: current?.error ?? null,
    fetchedAt: status === 'ready' ? fetchedAt : null,
    search: searchInput,
    setSearch: setSearchInput,
    reload: () => setAttempt((n) => n + 1),
  };
}
