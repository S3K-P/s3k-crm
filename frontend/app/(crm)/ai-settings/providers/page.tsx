'use client';

import { useState } from 'react';
import { Cpu, Loader2, PlugZap } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { loadAiStatus, useAiStatus } from '@/features/ai/useAiStatus';
import {
  PROVIDER_KEY_VARIABLE,
  PROVIDER_LABELS,
  PROVIDER_MODEL_VARIABLE,
  STATE_LABELS,
  availabilityOf,
  describeErrorCode,
  describeNotConfigured,
  formatCheckedAt,
  runAiHealthCheck,
  type AiConnectionState,
  type AiHealthCheck,
} from '@/features/ai/status';

/* ============================================================
   PROVIDERS & MODELS

   Which AI provider and model this deployment calls, whether a
   key is configured for it, and what the most recent real call
   found — all from `GET /ai/status`.

   "Test AI connection" sends one minimal real request to the
   configured model through `POST /ai/health` (`ai.ADMIN`) and
   shows exactly what came back. It spends a few tokens of
   provider quota, so it runs when an administrator presses it
   and never on its own.

   Credentials are configured in the backend environment and are
   never shown here or anywhere else in the interface.
   ============================================================ */

const BADGE_CLASS: Record<ReturnType<typeof availabilityOf> | 'verified', string> = {
  verified: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
  ready: 'border-[var(--border)] bg-[var(--surface-2)] txt-muted',
  not_configured: 'border-[var(--border)] bg-[var(--surface-2)] txt-muted',
  auth_failed: 'border-rose-500/30 bg-rose-500/10 text-rose-600',
  unavailable: 'border-amber-500/30 bg-amber-500/10 text-amber-600',
};

function StateBadge({ state }: { state: AiConnectionState }) {
  const tone = state === 'AVAILABLE' ? 'verified' : availabilityOf(state);
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11.5px] font-semibold',
        BADGE_CLASS[tone],
      )}
    >
      {STATE_LABELS[state]}
    </span>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bd grid gap-1 border-b py-3 last:border-b-0 sm:grid-cols-[180px_minmax(0,1fr)] sm:gap-4">
      <dt className="txt-muted text-[12.5px] font-medium">{label}</dt>
      <dd className="txt min-w-0 text-[13px]">{children}</dd>
    </div>
  );
}

export default function AIProvidersPage() {
  const { can } = useAuth();
  const isAdmin = can('ai', 'ADMIN');
  const { status, error } = useAiStatus();

  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<AiHealthCheck | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  async function testConnection() {
    setTesting(true);
    setTestError(null);
    try {
      const check = await runAiHealthCheck();
      setResult(check);
      // The backend recorded this verdict; every AI screen should now agree.
      void loadAiStatus(true);
    } catch (caught) {
      setResult(null);
      setTestError(describeApiError(caught, 'The connection test could not be run.'));
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
          <Cpu className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Providers &amp; Models</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            The AI provider and model this deployment calls, and whether it answers.
          </p>
        </div>
      </div>

      {!status && <AiConnectionNotice status={null} error={error} />}

      {status && (
        <section className="surface bd rounded-2xl border px-5 py-2" aria-label="AI connection">
          <dl>
            <Row label="Provider">
              {PROVIDER_LABELS[status.provider]}
              <span className="txt-faint ml-2 font-mono text-[11.5px]">
                AI_PROVIDER={status.provider}
              </span>
            </Row>
            <Row label="Model">
              <span className="font-mono text-[12.5px]">{status.model ?? '—'}</span>
            </Row>
            <Row label="Configuration status">
              {status.configured ? (
                'Configured — a key is set for this provider.'
              ) : (
                <span>
                  Not configured.{' '}
                  <span className="txt-muted">
                    {isAdmin
                      ? describeNotConfigured(status)
                      : 'An administrator needs to add an AI provider key.'}
                  </span>
                </span>
              )}
            </Row>
            <Row label="Connection status">
              <div className="flex flex-wrap items-center gap-2">
                <StateBadge state={status.state} />
                <span className="txt-muted text-[12.5px]">
                  {status.checked_at
                    ? `Last checked ${formatCheckedAt(status.checked_at)} by ${
                        status.check_source === 'health_check' ? 'a connection test' : 'an AI request'
                      }${status.latency_ms !== null ? ` · ${status.latency_ms} ms` : ''}.`
                    : status.configured
                      ? 'Not verified by a real request yet.'
                      : ''}
                </span>
              </div>
              {status.error_code && availabilityOf(status.state) !== 'ready' && (
                <p className="txt-muted mt-1.5 text-[12.5px]">{describeErrorCode(status.error_code)}</p>
              )}
            </Row>
          </dl>
        </section>
      )}

      <section className="surface bd rounded-2xl border p-5" aria-label="Connection test">
        <h2 className="txt font-display text-[15px] font-bold">Test AI connection</h2>
        {isAdmin ? (
          <>
            <p className="txt-muted mt-1 text-[12.5px]">
              Sends one short request to the configured model and reports what came back. It uses
              a few tokens of provider quota.
            </p>
            <button
              type="button"
              onClick={() => void testConnection()}
              disabled={testing}
              className="btn-primary mt-4 inline-flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {testing ? (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
              ) : (
                <PlugZap className="h-4 w-4" aria-hidden="true" />
              )}
              {testing ? 'Testing…' : 'Test AI connection'}
            </button>

            {testError && (
              <p role="alert" className="mt-3 text-[12.5px] text-rose-600">
                {testError}
              </p>
            )}

            {result && (
              <div
                role="status"
                aria-label="Connection test result"
                className="bd mt-4 space-y-1.5 rounded-xl border p-4 text-[12.5px]"
                style={{ background: 'var(--surface-2)' }}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="txt font-semibold">Result:</span>
                  <StateBadge state={result.state} />
                </div>
                {result.state === 'AVAILABLE' ? (
                  <p className="txt-muted">
                    {PROVIDER_LABELS[result.provider]} answered from{' '}
                    <span className="font-mono">{result.responded_model ?? result.model}</span>
                    {result.latency_ms !== null ? ` in ${result.latency_ms} ms` : ''}.
                  </p>
                ) : result.state === 'NOT_CONFIGURED' ? (
                  <p className="txt-muted">
                    Nothing was sent: {describeErrorCode(result.error_code)}
                  </p>
                ) : (
                  <p className="txt-muted">
                    {describeErrorCode(result.error_code)}
                    {result.latency_ms !== null ? ` (after ${result.latency_ms} ms)` : ''}
                  </p>
                )}
              </div>
            )}
          </>
        ) : (
          <p className="txt-muted mt-1 text-[12.5px]">
            Only administrators can run a connection test.
          </p>
        )}
      </section>

      {isAdmin && status && (
        <section className="surface bd rounded-2xl border p-5" aria-label="How to configure">
          <h2 className="txt font-display text-[15px] font-bold">How AI is configured</h2>
          <p className="txt-muted mt-1 text-[12.5px]">
            Set in the backend environment — never in the browser. Keys are read only by the API
            and are not shown anywhere in this interface.
          </p>
          <ul className="txt mt-3 space-y-1.5 text-[12.5px]">
            <li>
              <code className="font-mono">AI_PROVIDER</code> — <code>anthropic</code> or{' '}
              <code>gemini</code>. Currently <code>{status.provider}</code>.
            </li>
            <li>
              <code className="font-mono">{PROVIDER_KEY_VARIABLE.anthropic}</code> — required when
              AI_PROVIDER is <code>anthropic</code>.
            </li>
            <li>
              <code className="font-mono">{PROVIDER_KEY_VARIABLE.gemini}</code> (or{' '}
              <code>GOOGLE_API_KEY</code>) — required when AI_PROVIDER is <code>gemini</code>.
            </li>
            <li>
              <code className="font-mono">{PROVIDER_MODEL_VARIABLE.anthropic}</code> /{' '}
              <code className="font-mono">{PROVIDER_MODEL_VARIABLE.gemini}</code> — the model for
              each provider.
            </li>
          </ul>
          <p className="txt-muted mt-3 text-[12.5px]">
            A key for the provider AI_PROVIDER does not select is ignored. After changing any of
            these, restart the API — on Railway, trigger a redeploy — then test the connection.
          </p>
        </section>
      )}
    </div>
  );
}
