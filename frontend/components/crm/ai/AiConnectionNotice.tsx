'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { CheckCircle2, CloudOff, KeyRound, Loader2, PlugZap, type LucideIcon } from 'lucide-react';

import { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { useAuth } from '@/context/AuthContext';
import {
  PROVIDER_KEY_VARIABLE,
  PROVIDER_LABELS,
  availabilityOf,
  describeErrorCode,
  describeNotConfigured,
  formatCheckedAt,
  type AiStatus,
} from '@/features/ai/status';

/* ============================================================
   AI CONNECTION NOTICE

   What an AI screen says about the AI connection, read from
   `GET /ai/status` and never assumed. Four answers that must
   not be conflated:

   - not configured      no key for the provider AI_PROVIDER selects
   - credential rejected a key is set and the provider refused it
   - unavailable         the last real call failed or timed out
   - ready               configured — and "connected" only once a
                         real model call has proved it

   "AI is not connected" is the first of those and nothing else.
   A screen whose feature has not been built yet passes
   `pending`, and when AI is ready it says the feature is coming
   next instead of blaming the connection for its absence.
   ============================================================ */

type Tone = 'neutral' | 'success' | 'warning' | 'danger';

const TONE_ICON_CLASS: Record<Tone, string> = {
  neutral: 'txt-faint',
  success: 'text-emerald-500',
  warning: 'text-amber-500',
  danger: 'text-rose-500',
};

function StatusCard({
  icon: Icon,
  tone,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  tone: Tone;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      role="status"
      className="surface bd flex flex-col items-center gap-3 rounded-2xl border px-6 py-12 text-center"
    >
      <div
        className="flex h-11 w-11 items-center justify-center rounded-full"
        style={{ background: 'var(--surface-2)' }}
      >
        <Icon className={`h-5 w-5 ${TONE_ICON_CLASS[tone]}`} aria-hidden="true" />
      </div>
      <div>
        <p className="txt text-[14px] font-semibold">{title}</p>
        <div className="txt-muted mx-auto mt-1.5 max-w-lg space-y-1.5 text-[12.5px] leading-relaxed">
          {children}
        </div>
      </div>
      {action}
    </div>
  );
}

export default function AiConnectionNotice({
  status,
  error,
  pending,
  consequence,
  hideWhenReady = false,
}: {
  status: AiStatus | null;
  /** The status request itself failed. */
  error: string | null;
  /** A screen whose AI feature does not exist yet. */
  pending?: { name: string; what: string };
  /** What the state means for this particular screen. */
  consequence?: string;
  /** Render nothing while loading or when AI is ready — for screens that work regardless. */
  hideWhenReady?: boolean;
}) {
  const { can } = useAuth();
  const isAdmin = can('ai', 'ADMIN');

  if (!status) {
    if (error) {
      return (
        <PartialDataNotice>The AI connection status could not be checked: {error}</PartialDataNotice>
      );
    }
    if (hideWhenReady) return null;
    return (
      <div
        role="status"
        aria-busy="true"
        className="surface bd txt-muted flex items-center gap-2.5 rounded-2xl border px-5 py-4 text-[12.5px]"
      >
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
        Checking the AI connection…
      </div>
    );
  }

  const provider = PROVIDER_LABELS[status.provider];
  const checked = status.checked_at ? `Checked ${formatCheckedAt(status.checked_at)}.` : null;
  const settingsLink = isAdmin ? (
    <Link
      href="/ai-settings/providers"
      className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
    >
      Open Providers &amp; Models
    </Link>
  ) : null;

  switch (availabilityOf(status.state)) {
    case 'not_configured':
      return (
        <StatusCard icon={PlugZap} tone="neutral" title="AI is not connected" action={settingsLink}>
          <p>
            {isAdmin
              ? describeNotConfigured(status)
              : 'No AI provider is configured for this deployment. An administrator needs to add one before AI features can run.'}
          </p>
          {consequence && <p>{consequence}</p>}
        </StatusCard>
      );

    case 'auth_failed':
      return (
        <StatusCard
          icon={KeyRound}
          tone="danger"
          title="The AI provider rejected its credential"
          action={settingsLink}
        >
          <p>
            {provider} refused the configured API key, so AI requests cannot run.{' '}
            {isAdmin
              ? `Replace ${PROVIDER_KEY_VARIABLE[status.provider]} in the backend environment and restart the API.`
              : 'An administrator needs to update the AI provider key.'}{' '}
            {checked}
          </p>
          {consequence && <p>{consequence}</p>}
        </StatusCard>
      );

    case 'unavailable':
      return (
        <StatusCard
          icon={CloudOff}
          tone="warning"
          title={status.state === 'TIMEOUT' ? 'The AI provider timed out' : 'The AI provider is not responding'}
          action={settingsLink}
        >
          <p>
            The last request to {provider} failed: {describeErrorCode(status.error_code)} {checked}
          </p>
          {consequence && <p>{consequence}</p>}
        </StatusCard>
      );

    case 'ready':
      if (!pending || hideWhenReady) return null;
      return (
        <StatusCard
          icon={CheckCircle2}
          tone={status.state === 'AVAILABLE' ? 'success' : 'neutral'}
          title={status.state === 'AVAILABLE' ? 'AI is connected' : 'AI is configured'}
        >
          <p>
            {status.state === 'AVAILABLE'
              ? `${provider} (${status.model}) answered a real request. ${checked ?? ''}`
              : `${provider} (${status.model}) is configured. The connection has not been verified yet${isAdmin ? ' — run a test from Providers & Models' : ''}.`}
          </p>
          <p className="txt font-medium">{pending.name} is coming next.</p>
          <p>{pending.what}</p>
        </StatusCard>
      );
  }
}
