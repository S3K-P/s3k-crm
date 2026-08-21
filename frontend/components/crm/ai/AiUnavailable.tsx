'use client';

import type { LucideIcon } from 'lucide-react';

import NotConfigured from '@/components/crm/shared/NotConfigured';

/* ============================================================
   AI UNAVAILABLE

   The shared body for every AI screen.

   No AI gateway exists in this system: no provider is
   configured, no credential is stored, no model is called, and
   ADR-016 defers the whole capability to Phase 5. Every AI page
   previously rendered a fixed demonstration dataset — connected
   providers, running agents with "last run 2 mins ago", request
   counts, cost charts. None of it was measured, and none of it
   was distinguishable from real telemetry on screen.

   The pages, their route and their navigation are unchanged.
   What is gone is the claim that any of it is live.
   ============================================================ */

export default function AiUnavailable({
  title,
  subtitle,
  icon: Icon,
  what,
}: {
  /** Page heading, unchanged from the original screen. */
  title: string;
  /** One line describing what the screen is for. */
  subtitle: string;
  icon: LucideIcon;
  /** What this particular screen would show once the gateway exists. */
  what: string;
}) {
  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">{title}</h1>
          <p className="txt-muted mt-0.5 text-[13px]">{subtitle}</p>
        </div>
      </div>

      <NotConfigured
        title="AI is not connected"
        description={`${what} None of this is available: there is no AI gateway in this system, no provider credentials are stored, and no model is ever called. Nothing on this screen is measured or live.`}
        requires="AI gateway (ADR-016, Phase 5)"
      />
    </div>
  );
}
