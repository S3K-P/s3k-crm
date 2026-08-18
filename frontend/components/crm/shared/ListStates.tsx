'use client';

import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';

/* ============================================================
   LIST STATES
   The three non-data states every CRM list screen needs, in one
   place so they look and behave the same everywhere.

   There is deliberately no "fall back to sample rows" state. An
   empty table means the organization genuinely has no records;
   an error means the request failed and says so. Substituting
   invented rows for either would be worse than showing nothing.
   ============================================================ */

export function ListError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="surface bd flex flex-col items-center gap-3 rounded-2xl border py-12 text-center"
    >
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-pink-500 to-rose-500">
        <AlertTriangle className="h-5 w-5 text-white" aria-hidden="true" />
      </div>
      <div>
        <p className="txt text-[14px] font-semibold">Couldn&apos;t load this list</p>
        <p className="txt-muted mx-auto mt-1 max-w-md text-[12.5px]">{message}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="ctl bd mt-1 inline-flex items-center gap-1.5 rounded-xl border px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        Try again
      </button>
    </div>
  );
}

export function ListEmpty({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <div
        className="flex h-11 w-11 items-center justify-center rounded-full"
        style={{ background: 'var(--surface-2)' }}
      >
        <Inbox className="txt-faint h-5 w-5" aria-hidden="true" />
      </div>
      <div>
        <p className="txt text-[14px] font-semibold">{title}</p>
        {hint && <p className="txt-muted mx-auto mt-1 max-w-md text-[12.5px]">{hint}</p>}
      </div>
      {action}
    </div>
  );
}

/** Inline error shown inside a form, above the submit button. */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="flex items-start gap-2 text-[12.5px] font-medium text-red-500"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

/** Page-size-aware summary line, e.g. "Showing 25 of 132". */
export function ResultCount({ shown, total }: { shown: number; total: number }) {
  if (total === 0) return null;
  return (
    <p className="txt-faint text-[12px] font-medium">
      Showing {shown} of {total}
    </p>
  );
}
