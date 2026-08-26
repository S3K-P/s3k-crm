'use client';

import { PlugZap } from 'lucide-react';

/* ============================================================
   NOT CONFIGURED

   The honest state for a screen whose backend does not exist
   yet.

   It replaces invented numbers, not the screen: the page, its
   navigation and its layout stay exactly where they were. What
   goes is the pretence that "1,245 users" or "99.9% uptime" was
   ever measured. A stakeholder reading a fabricated dashboard
   cannot tell it apart from a real one, and will plan against
   it — which is the specific failure this component exists to
   prevent.

   `requires` names the missing backend so the gap is legible
   from the screen itself rather than only in a status report.
   ============================================================ */

export default function NotConfigured({
  title,
  description,
  requires,
  compact = false,
}: {
  /** What this screen would show once the backend exists. */
  title: string;
  /** One or two sentences on what is and is not available. */
  description: string;
  /** The backend work this screen waits on, e.g. "Audit log service". */
  requires?: string;
  /** Denser presentation, for a panel inside a page rather than a whole page. */
  compact?: boolean;
}) {
  return (
    <div
      role="status"
      className={`surface bd flex flex-col items-center gap-3 rounded-2xl border text-center ${
        compact ? 'px-5 py-8' : 'px-6 py-14'
      }`}
    >
      <div
        className="flex items-center justify-center rounded-full"
        style={{
          background: 'var(--surface-2)',
          height: compact ? '2.25rem' : '2.75rem',
          width: compact ? '2.25rem' : '2.75rem',
        }}
      >
        <PlugZap
          className={`txt-faint ${compact ? 'h-4 w-4' : 'h-5 w-5'}`}
          aria-hidden="true"
        />
      </div>

      <div>
        <p className={`txt font-semibold ${compact ? 'text-[13px]' : 'text-[14px]'}`}>{title}</p>
        <p className="txt-muted mx-auto mt-1.5 max-w-lg text-[12.5px] leading-relaxed">
          {description}
        </p>
      </div>

      {requires && (
        <p className="txt-faint mt-1 text-[11.5px] font-medium">
          Waiting on:{' '}
          <span className="bd rounded-md border px-1.5 py-0.5 font-mono text-[11px]">
            {requires}
          </span>
        </p>
      )}
    </div>
  );
}

/**
 * Inline banner for a screen that is *partly* real.
 *
 * Used where genuine data is on the page and one section of it is not
 * available — the qualification queue, for instance, which shows real leads
 * but cannot show a stored scorecard.
 */
export function PartialDataNotice({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="status"
      className="bd flex items-start gap-2.5 rounded-xl border px-3.5 py-3"
      style={{ background: 'var(--surface-2)' }}
    >
      <PlugZap className="txt-faint mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <p className="txt-muted text-[12px] leading-relaxed">{children}</p>
    </div>
  );
}
