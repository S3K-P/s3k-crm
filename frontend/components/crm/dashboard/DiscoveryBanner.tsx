'use client';

import { useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import Link from 'next/link';

/* ============================================================
   DISCOVERY BANNER
   Dismissible nudge pointing at Customize and AI Insights.
   Local component state only, matching the mockup: dismissing it
   just removes it for this page visit, nothing is persisted.
   ============================================================ */

export default function DiscoveryBanner() {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <div
      className="flex items-center gap-3.5 rounded-2xl border p-3.5"
      style={{
        background: 'linear-gradient(120deg, var(--accent-soft), transparent 70%)',
        borderColor: 'var(--accent-soft)',
      }}
    >
      <Sparkles className="h-[22px] w-[22px] shrink-0" style={{ color: 'var(--accent)' }} />
      <div className="flex-1">
        <div className="txt text-[13px] font-bold">There&apos;s more to see here</div>
        <div className="text-[12px]" style={{ color: 'var(--muted)' }}>
          Add cards, reorder your layout, or explore AI Insights for recommended next actions.
        </div>
      </div>
      <Link
        href="/ai/insights"
        className="shrink-0 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:bg-[var(--surface-2)]"
        style={{ borderColor: 'var(--border)' }}
      >
        Explore AI Insights
      </Link>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="shrink-0 rounded-lg p-1.5 transition hover:bg-[var(--surface-2)]"
        style={{ color: 'var(--muted)' }}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
