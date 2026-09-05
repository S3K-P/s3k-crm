'use client';

import { useEffect, useRef, useState } from 'react';
import { Bell, BellOff, CheckCheck } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useNotifications } from '@/features/platform/notifications/useNotifications';
import type { Notification } from '@/features/platform/notifications';

/* ============================================================
   NOTIFICATION BELL

   Same interaction shape as AccountMenu: a chrome button opens an
   absolutely-positioned panel, closed by an outside click or Escape.

   Clicking an unread notification marks it read but does not yet
   navigate to the record it is about — entity_type/entity_id are
   there for a future "open the record" action once every module
   has a stable detail route to hand it to. For now the inbox is
   read here and the underlying record is found the way it always
   was, through its own list.
   ============================================================ */

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function NotificationRow({
  notification,
  onRead,
}: {
  notification: Notification;
  onRead: (id: string) => void;
}) {
  const unread = !notification.read_at;
  return (
    <button
      type="button"
      role="menuitem"
      onClick={() => unread && onRead(notification.id)}
      className={cn(
        'flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left transition-colors hover:surface-2',
        unread && 'bg-[var(--accent-soft)]',
      )}
    >
      <span
        className={cn(
          'mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full',
          unread ? 'bg-[var(--accent)]' : 'bg-transparent',
        )}
        aria-hidden="true"
      />
      <span className="min-w-0 flex-1">
        <span className="txt block truncate text-[12.5px] font-semibold">
          {notification.title}
        </span>
        {notification.body && (
          <span className="txt-muted mt-0.5 block truncate text-[12px]">{notification.body}</span>
        )}
        <span className="txt-faint mt-0.5 block text-[11px]">{timeAgo(notification.created_at)}</span>
      </span>
    </button>
  );
}

export default function NotificationBell() {
  const { unreadCount, notifications, listLoading, error, loadList, markRead, markAllRead } =
    useNotifications();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const handleToggle = () => {
    const next = !open;
    setOpen(next);
    if (next) void loadList();
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={handleToggle}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={unreadCount > 0 ? `${unreadCount} unread notifications` : 'Notifications'}
        className="ctl txt-muted relative grid h-9 w-9 place-items-center rounded-[10px] transition hover:opacity-80"
      >
        <Bell className="h-[17px] w-[17px]" />
        {unreadCount > 0 && (
          <span className="absolute right-1 top-1 grid h-4 min-w-[16px] place-items-center rounded-full bg-rose-500 px-1 text-[9.5px] font-bold leading-none text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="surface bd absolute right-0 top-full z-50 mt-2 w-[320px] overflow-hidden rounded-xl border shadow-[0_20px_50px_-20px_rgba(0,0,0,0.35)]"
        >
          <div className="bd flex items-center justify-between border-b px-3.5 py-2.5">
            <p className="txt text-[12.5px] font-bold">Notifications</p>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void markAllRead()}
                className="flex items-center gap-1 text-[11.5px] font-semibold transition hover:opacity-80"
                style={{ color: 'var(--accent)' }}
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-[360px] overflow-y-auto">
            {listLoading && notifications.length === 0 && (
              <p className="txt-faint px-3.5 py-6 text-center text-[12.5px]">Loading…</p>
            )}
            {error && (
              <p className="px-3.5 py-6 text-center text-[12.5px] text-rose-500">{error}</p>
            )}
            {!listLoading && !error && notifications.length === 0 && (
              <div className="flex flex-col items-center gap-2 px-3.5 py-8 text-center">
                <BellOff className="txt-faint h-5 w-5" aria-hidden="true" />
                <p className="txt-muted text-[12.5px] font-medium">You&apos;re all caught up.</p>
              </div>
            )}
            {notifications.map((notification) => (
              <NotificationRow
                key={notification.id}
                notification={notification}
                onRead={(id) => void markRead(id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
