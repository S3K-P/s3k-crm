'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '@/context/AuthContext';
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  unreadNotificationCount,
  type Notification,
} from '@/features/platform/notifications';

/* ============================================================
   NOTIFICATION BELL STATE

   Two things happen on different schedules, on purpose:

   * the unread COUNT is polled continuously (every 30s) so the
     badge stays current whether or not the panel is open — the
     bell is the one piece of chrome that has to reflect reality
     without the viewer doing anything;
   * the LIST is fetched only when the panel opens, and again on
     every mark-read action. Polling the full list on the same
     timer as the count would mean twenty API calls a minute for
     something nobody is looking at most of the time.

   Same "no synchronous setState inside an effect" discipline as
   `usePlatformApps`: state is written only from event handlers
   or after an `await`, and every async effect body guards against
   a stale response landing after the component (or the active
   organization) has moved on.
   ============================================================ */

const POLL_INTERVAL_MS = 30_000;

interface NotificationBellState {
  unreadCount: number;
  notifications: Notification[];
  listLoading: boolean;
  error: string | null;
  /** Fetch the list — call when the panel opens. */
  loadList: () => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

export function useNotifications(): NotificationBellState {
  const { isAuthenticated, activeOrganizationId } = useAuth();
  const canFetch = isAuthenticated && activeOrganizationId !== null;

  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards a poll response that resolves after the component unmounted or
  // the organization changed mid-flight, the same shape `usePlatformApps`
  // uses for its own effect.
  const cancelledRef = useRef(false);

  const refreshUnreadCount = useCallback(async () => {
    if (!canFetch) return;
    try {
      const { unread_count: count } = await unreadNotificationCount();
      if (!cancelledRef.current) setUnreadCount(count);
    } catch {
      // A transient failure leaves the badge at its last known value rather
      // than blanking it — a stale count is a better guess than zero.
    }
  }, [canFetch]);

  const loadList = useCallback(async () => {
    if (!canFetch) return;
    setListLoading(true);
    try {
      const page = await listNotifications({ page_size: 20 });
      if (cancelledRef.current) return;
      setNotifications(page.data);
      setError(null);
    } catch {
      if (!cancelledRef.current) setError('Unable to load notifications right now.');
    } finally {
      if (!cancelledRef.current) setListLoading(false);
    }
  }, [canFetch]);

  const markRead = useCallback(
    async (id: string) => {
      // Optimistic: the click that opened this action already told the
      // viewer their intent, and reverting a rare failure on the next poll
      // costs less attention than a badge that lags a visible click.
      setNotifications((current) =>
        current.map((item) =>
          item.id === id && !item.read_at
            ? { ...item, read_at: new Date().toISOString() }
            : item,
        ),
      );
      setUnreadCount((count) => Math.max(0, count - 1));
      try {
        await markNotificationRead(id);
      } catch {
        await Promise.all([loadList(), refreshUnreadCount()]);
      }
    },
    [loadList, refreshUnreadCount],
  );

  const markAllRead = useCallback(async () => {
    const now = new Date().toISOString();
    setNotifications((current) =>
      current.map((item) => (item.read_at ? item : { ...item, read_at: now })),
    );
    setUnreadCount(0);
    try {
      await markAllNotificationsRead();
    } catch {
      await Promise.all([loadList(), refreshUnreadCount()]);
    }
  }, [loadList, refreshUnreadCount]);

  useEffect(() => {
    cancelledRef.current = false;
    // No fetch and no setState here when there is nothing to poll for — the
    // returned values below derive the signed-out/tenant-less answer instead
    // of this effect writing it, the same trick `usePlatformApps` uses. A
    // synchronous `setState` in an effect body schedules a second render
    // pass before the first has painted (`react-hooks/set-state-in-effect`).
    if (!canFetch) {
      return () => {
        cancelledRef.current = true;
      };
    }

    // The first poll, as an async IIFE rather than a direct call to the
    // memoized callback: `react-hooks/set-state-in-effect` cannot see through
    // a function reference to confirm every write inside it happens after an
    // `await`, so it flags the call itself. Declaring the body inline is what
    // `usePlatformApps` does for the same reason.
    void (async () => {
      if (cancelledRef.current) return;
      await refreshUnreadCount();
    })();
    const interval = window.setInterval(() => void refreshUnreadCount(), POLL_INTERVAL_MS);
    return () => {
      cancelledRef.current = true;
      window.clearInterval(interval);
    };
    // `refreshUnreadCount` is stable for a given `canFetch`/organization, and
    // including it here (rather than omitting it) is what makes the poll
    // restart cleanly on an organization switch instead of continuing to
    // poll for the tenant the viewer just left.
  }, [canFetch, refreshUnreadCount]);

  return {
    // Never leak the previous tenant's (or a signed-out session's) inbox.
    unreadCount: canFetch ? unreadCount : 0,
    notifications: canFetch ? notifications : [],
    listLoading,
    error,
    loadList,
    markRead,
    markAllRead,
  };
}

export default useNotifications;
