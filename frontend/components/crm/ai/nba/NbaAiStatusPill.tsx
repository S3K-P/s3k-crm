import { Loader2 } from 'lucide-react';

import {
  PROVIDER_LABELS,
  STATE_LABELS,
  availabilityOf,
  type AiStatus,
} from '@/features/ai/status';

/* ============================================================
   NBA AI STATUS PILL

   A compact read of `GET /ai/status` for the page header. The
   provider name is whatever the backend reports it is configured
   with — this never assumes one — and "Connected" appears only
   once a real model call has proved it (`AVAILABLE`).
   ============================================================ */

const DOT: Record<string, string> = {
  connected: 'bg-emerald-500',
  configured: 'bg-[var(--accent)]',
  off: 'bg-[var(--faint)]',
  warning: 'bg-amber-500',
  danger: 'bg-rose-500',
};

export default function NbaAiStatusPill({
  status,
  error,
  loading,
}: {
  status: AiStatus | null;
  error: string | null;
  loading: boolean;
}) {
  let dot = DOT.off;
  let text: string;
  let title: string | undefined;

  if (!status) {
    if (loading) {
      return (
        <span className="ctl txt-muted inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-[12px] font-semibold">
          <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden="true" /> Checking AI…
        </span>
      );
    }
    dot = DOT.warning;
    text = 'AI status unavailable';
    title = error ?? undefined;
  } else {
    const provider = PROVIDER_LABELS[status.provider];
    title = `${provider}${status.model ? ` (${status.model})` : ''} — ${STATE_LABELS[status.state]}`;
    switch (availabilityOf(status.state)) {
      case 'ready':
        dot = status.state === 'AVAILABLE' ? DOT.connected : DOT.configured;
        text = `${provider} · ${status.state === 'AVAILABLE' ? 'Connected' : 'Configured'}`;
        break;
      case 'not_configured':
        text = 'AI not connected';
        break;
      case 'auth_failed':
        dot = DOT.danger;
        text = `${provider} · Key rejected`;
        break;
      case 'unavailable':
        dot = DOT.warning;
        text = `${provider} · Not responding`;
        break;
    }
  }

  return (
    <span
      role="status"
      title={title}
      className="ctl txt inline-flex items-center gap-2 whitespace-nowrap rounded-full px-3 py-1.5 text-[12px] font-semibold"
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      {text}
    </span>
  );
}
