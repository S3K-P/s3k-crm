'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import { fetchHomeDashboardLayout, saveHomeDashboardLayout } from '@/features/crm/dashboard/api';
import type { HomeCardConfig, HomeCardType } from '@/features/crm/dashboard/types';

/* ============================================================
   USE HOME DASHBOARD LAYOUT

   Loads the signed-in user's saved "Customize dashboard" layout
   for the fixed home screen, and keeps the backend in sync with
   it. Not related to the user-built "configurable dashboards"
   (`Dashboard`/`DashboardComponent`, `/boards/...`) feature
   elsewhere in this module — this is the home page's own
   card-visibility/order preference.

   Reordering and show/hide update local state immediately — the
   grid must not wait on a round trip to react to a drag — and the
   save to the server is debounced, so a drag gesture that moves a
   card through several positions sends one PUT, not one per frame.
   ============================================================ */

const SAVE_DEBOUNCE_MS = 700;

export type HomeDashboardLayoutStatus = 'loading' | 'ready' | 'error';

export interface UseHomeDashboardLayout {
  status: HomeDashboardLayoutStatus;
  /** The full saved order, visible and hidden cards alike. */
  cards: HomeCardConfig[];
  /** `cards` filtered to what should render in the grid right now. */
  visibleCards: HomeCardConfig[];
  hiddenCards: HomeCardConfig[];
  /** True while a save from an earlier change is still in flight or pending. */
  saving: boolean;
  error: string | null;
  /** Reorder within the *visible* set — `fromIndex`/`toIndex` index into `visibleCards`. */
  reorderVisible: (fromIndex: number, toIndex: number) => void;
  setVisible: (cardType: HomeCardType, visible: boolean) => void;
}

export function useHomeDashboardLayout(): UseHomeDashboardLayout {
  const { loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();

  const [cards, setCards] = useState<HomeCardConfig[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // A layout is per (user, organization): switching organizations means a
  // different saved layout, so the load key includes it. `loadedKey` only
  // advances once a request for that key has actually settled, which is how
  // `status` is derived below without setting it synchronously inside the
  // effect body.
  const loadKey = activeOrganizationId ?? 'none';
  const [loadedKey, setLoadedKey] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;

    let cancelled = false;

    void (async () => {
      try {
        const layout = await fetchHomeDashboardLayout();
        if (!cancelled) {
          setCards(layout.cards);
          setError(null);
          setLoadedKey(loadKey);
        }
      } catch {
        if (!cancelled) {
          setError('Could not load your saved dashboard layout. Showing the default.');
          setLoadedKey(loadKey);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated, loadKey]);

  const status: HomeDashboardLayoutStatus =
    loadedKey !== loadKey ? 'loading' : error ? 'error' : 'ready';

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const persist = useCallback((next: HomeCardConfig[]) => {
    setCards(next);
    setSaving(true);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      void saveHomeDashboardLayout({ cards: next })
        .catch(() => {
          // The optimistic local order stands; the next full reload (e.g. a
          // revisit) reconciles with whatever the server actually holds.
        })
        .finally(() => setSaving(false));
    }, SAVE_DEBOUNCE_MS);
  }, []);

  const reorderVisible = useCallback(
    (fromIndex: number, toIndex: number) => {
      setCards((current) => {
        const visible = current.filter((card) => card.visible);
        if (fromIndex < 0 || fromIndex >= visible.length) return current;
        const reordered = [...visible];
        const [moved] = reordered.splice(fromIndex, 1);
        reordered.splice(toIndex, 0, moved);

        // Re-merge: walk the full order and slot the newly-ordered visible
        // cards back in, so a hidden card's position is never disturbed by
        // a drag it was not part of.
        let cursor = 0;
        const next = current.map((card) => (card.visible ? reordered[cursor++] : card));
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const setVisible = useCallback(
    (cardType: HomeCardType, visible: boolean) => {
      setCards((current) => {
        const next = current.map((card) =>
          card.card_type === cardType ? { ...card, visible } : card,
        );
        persist(next);
        return next;
      });
    },
    [persist],
  );

  return {
    status,
    cards,
    visibleCards: cards.filter((card) => card.visible),
    hiddenCards: cards.filter((card) => !card.visible),
    saving,
    error,
    reorderVisible,
    setVisible,
  };
}
