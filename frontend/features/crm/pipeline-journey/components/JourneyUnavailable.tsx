'use client';

import { AlertCircle, RotateCw } from 'lucide-react';

/* ============================================================
   JOURNEY UNAVAILABLE

   A panel that says what it would show and what it is waiting
   on, in place of a panel filled with invented figures.

   This is the pattern CR06 established for the screens that had
   no backend: "each page names the backend it waits on". It is
   deliberately plain — a greyed, dashed panel reads as *absent*
   at a glance, where a styled card showing zeroes reads as a
   measurement of zero. The distinction matters most to the
   person who is not reading carefully.
   ============================================================ */

export default function JourneyUnavailable({
  title,
  detail,
  onRetry,
}: {
  title: string;
  detail: string;
  /** Supplied only when the failure is retryable, e.g. a request error. */
  onRetry?: () => void;
}) {
  return (
    <div className="bd surface flex flex-col gap-2 rounded-2xl border border-dashed p-5">
      <div className="flex items-center gap-2">
        <AlertCircle className="txt-faint h-4 w-4 shrink-0" aria-hidden="true" />
        <h3 className="txt text-[13.5px] font-semibold">{title}</h3>
      </div>

      <p className="txt-faint text-[12.5px] leading-relaxed">{detail}</p>

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="ctl txt-muted mt-1 flex w-fit items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
        >
          <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  );
}
