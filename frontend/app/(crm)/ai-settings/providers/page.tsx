'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Cpu,
  KeyRound,
  Loader2,
  Lock,
  Plug,
  RotateCcw,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';

import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  listProviders,
  makeProviderDefault,
  removeProviderCredential,
  saveProviderCredential,
  testProviderCredential,
  STATUS_LABEL,
  type AiProvider,
  type AiProvidersPayload,
} from '@/features/ai/providers';

/* ============================================================
   PROVIDERS & MODELS

   Where an administrator connects AI, so that doing so no
   longer means editing `backend/.env` and redeploying.

   **The key goes one way.** It is typed here, sent once, and
   never comes back — every subsequent render shows the masked
   form the server stored. The input is cleared on success so
   the plaintext does not linger in the DOM, and there is no
   "reveal" affordance because there is no endpoint that could
   serve one.

   Admin-only. The backend enforces `ai.ADMIN` on every route
   below; hiding the form for anyone else is a courtesy, not the
   control.
   ============================================================ */

export default function AIProvidersPage() {
  const { can, loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();
  const isAdmin = can('ai', 'ADMIN');

  const [payload, setPayload] = useState<AiProvidersPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  /** Which provider has an action in flight, so only its button spins. */
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const loaded = await listProviders();
    setPayload(loaded);
    setLoadError(null);
  }, []);

  // `loading` starts false and is turned on by the fetch itself — starting it
  // true would force the not-allowed branch to switch it off synchronously
  // inside the effect, which is the cascading-render pattern the lint rule
  // exists to catch.
  useEffect(() => {
    if (authLoading || !isAuthenticated || !isAdmin) return;
    let cancelled = false;

    void (async () => {
      setLoading(true);
      try {
        const loaded = await listProviders();
        if (!cancelled) {
          setPayload(loaded);
          setLoadError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setPayload(null);
          setLoadError(describeApiError(caught, 'Providers could not be loaded.'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // `activeOrganizationId` is a dependency because credentials belong to the
    // organization: switching tenants must re-ask rather than show the last
    // one's configuration.
  }, [authLoading, isAuthenticated, isAdmin, activeOrganizationId]);

  if (authLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="txt-muted h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-5xl p-6 lg:p-8">
        <Header />
        <AiEmptyState
          icon={Lock}
          title="Administrator access required"
          description="Connecting an AI provider changes what the whole organization can run, and what it spends. Ask an administrator to configure it."
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6 lg:p-8">
      <Header />

      {loading && !payload && (
        <p className="txt-muted flex items-center gap-2 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          Loading providers…
        </p>
      )}

      {loadError && (
        <p role="alert" className="flex items-center gap-2 text-[13px] font-medium text-red-500">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {loadError}
        </p>
      )}

      {payload && (
        <>
          {/* Deployment cannot store secrets at all — a different problem from
              a provider simply being unconfigured, so it gets its own notice
              with the specific thing an operator must do. */}
          {!payload.storage_available && (
            <div className="surface bd rounded-xl border border-l-2 border-l-amber-500 p-4">
              <p className="txt text-[13.5px] font-semibold">
                Credential storage is not enabled on this deployment
              </p>
              <p className="txt-muted mt-1 text-[12.5px]">
                Keys cannot be saved until an operator sets{' '}
                <code className="ctl px-1 py-0.5 text-[11.5px]">
                  AI_CREDENTIAL_ENCRYPTION_KEY
                </code>{' '}
                in the backend environment. AI can still run from a
                deployment-wide key if one is configured there.
              </p>
            </div>
          )}

          {/* Connected, but on the deployment key rather than anything stored
              here. Without saying so, "Connected" beside "Not configured"
              reads as a contradiction. */}
          {payload.using_environment_fallback && (
            <div
              className="rounded-xl p-4"
              style={{ background: 'var(--accent-soft)' }}
            >
              <p className="txt text-[13.5px] font-semibold">
                Running on the deployment key
              </p>
              <p className="txt-muted mt-1 text-[12.5px]">
                AI is connected using this deployment&apos;s environment
                credential. Adding a key below overrides it for this
                organization only.
              </p>
            </div>
          )}

          <div className="space-y-4">
            {payload.providers.map((provider) => (
              <ProviderCard
                key={provider.provider}
                provider={provider}
                storageAvailable={payload.storage_available}
                busy={busy === provider.provider}
                anyBusy={busy !== null}
                onBusyChange={(value) => setBusy(value ? provider.provider : null)}
                onChanged={load}
              />
            ))}
          </div>

          {payload.providers.length === 0 && (
            <AiEmptyState
              icon={Cpu}
              title="No providers available"
              description="This deployment has no AI provider implementations compiled in."
            />
          )}
        </>
      )}
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-center gap-3.5">
      <div
        className="grid h-11 w-11 shrink-0 place-items-center rounded-xl"
        style={{ background: 'var(--accent-soft)' }}
      >
        <Cpu className="h-5 w-5 accent" aria-hidden="true" />
      </div>
      <div>
        <h1 className="font-display txt text-[20px] font-extrabold tracking-tight">
          Providers &amp; Models
        </h1>
        <p className="txt-muted text-[13px]">
          Connect an AI provider for this organization. Keys are encrypted and
          never shown again after saving.
        </p>
      </div>
    </div>
  );
}

function StatusPill({ provider }: { provider: AiProvider }) {
  if (!provider.configured || !provider.status) {
    return (
      <span className="status-badge txt-faint text-[10.5px] font-bold uppercase tracking-wider">
        Not configured
      </span>
    );
  }
  const tone =
    provider.status === 'CONNECTED'
      ? { color: 'var(--accent)' }
      : provider.status === 'INVALID'
        ? { color: '#ef4444' }
        : undefined;
  return (
    <span
      className="status-badge text-[10.5px] font-bold uppercase tracking-wider"
      style={tone}
    >
      {STATUS_LABEL[provider.status]}
    </span>
  );
}

function ProviderCard({
  provider,
  storageAvailable,
  busy,
  anyBusy,
  onBusyChange,
  onChanged,
}: {
  provider: AiProvider;
  storageAvailable: boolean;
  busy: boolean;
  anyBusy: boolean;
  onBusyChange: (busy: boolean) => void;
  onChanged: () => Promise<void>;
}) {
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState<string | null>(null);

  const run = async (
    action: () => Promise<{ ok?: boolean; error?: string | null } | unknown>,
    successMessage: string,
  ) => {
    if (anyBusy) return;
    onBusyChange(true);
    setError(null);
    try {
      const result = (await action()) as { ok?: boolean; error?: string | null };
      // A save or a test resolves successfully even when the provider rejected
      // the key — the HTTP call worked, the credential did not. Reporting that
      // as a success toast would be the opposite of what happened.
      if (result && result.ok === false) {
        setError(result.error ?? 'The provider rejected this key.');
        toast.error('The provider rejected this key.');
      } else {
        toast.success(successMessage);
      }
      await onChanged();
    } catch (caught) {
      const described = describeApiError(caught, 'That action could not be completed.');
      setError(described);
      toast.error(described);
    } finally {
      onBusyChange(false);
    }
  };

  const save = async () => {
    const key = apiKey.trim();
    if (!key) return;
    await run(() => saveProviderCredential(provider.provider, key), 'Provider connected.');
    // Cleared whatever the outcome: the plaintext has served its purpose and
    // has no reason to stay in the DOM.
    setApiKey('');
  };

  return (
    <section className="surface bd rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="surface-2 grid h-10 w-10 shrink-0 place-items-center rounded-lg">
            <Plug className="txt-muted h-4.5 w-4.5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display txt text-[15px] font-bold">{provider.label}</h2>
              <StatusPill provider={provider} />
              {provider.configured && provider.is_default && (
                <span
                  className="text-[10px] font-bold uppercase tracking-wider"
                  style={{ color: 'var(--accent)' }}
                >
                  Active
                </span>
              )}
            </div>
            <p className="txt-muted mt-0.5 text-[12.5px]">
              Model <code className="ctl px-1 py-0.5 text-[11.5px]">{provider.model}</code>
            </p>
          </div>
        </div>

        {provider.configured && (
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() =>
                void run(() => testProviderCredential(provider.provider), 'Connection verified.')
              }
              disabled={anyBusy}
              className="bd txt flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              Test connection
            </button>
            {!provider.is_default && (
              <button
                type="button"
                onClick={() =>
                  void run(
                    () => makeProviderDefault(provider.provider),
                    'Set as the active provider.',
                  )
                }
                disabled={anyBusy}
                className="bd txt rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:opacity-50"
              >
                Make active
              </button>
            )}
            <button
              type="button"
              onClick={() =>
                void run(
                  () => removeProviderCredential(provider.provider),
                  'Credential removed.',
                )
              }
              disabled={anyBusy}
              aria-label={`Remove the ${provider.label} credential`}
              className="bd txt-muted rounded-lg border px-2.5 py-1.5 transition hover:text-red-500 disabled:opacity-50"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {/* Stored credential — masked, and that is the only form there is. */}
      {provider.configured && (
        <div className="bd mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-t pt-4 text-[12.5px]">
          <span className="txt-muted">
            Key <code className="ctl ml-1 px-1.5 py-0.5">{provider.masked_key}</code>
          </span>
          <span className="txt-muted">
            Last tested{' '}
            <span className="txt">
              {provider.last_tested_at
                ? new Date(provider.last_tested_at).toLocaleString()
                : 'never'}
            </span>
          </span>
        </div>
      )}

      {provider.last_test_error && !error && (
        <p className="mt-3 flex items-start gap-2 text-[12.5px] font-medium text-red-500">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {provider.last_test_error}
        </p>
      )}

      {error && (
        <p role="alert" className="mt-3 flex items-start gap-2 text-[12.5px] font-medium text-red-500">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}

      {/* Add or replace. Present even when configured, because rotating a key
          is the same action as setting the first one. */}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
        className="mt-4 flex flex-wrap items-end gap-3"
      >
        <div className="min-w-[16rem] flex-1 space-y-1.5">
          <label
            htmlFor={`key-${provider.provider}`}
            className="txt text-[13px] font-semibold"
          >
            {provider.configured ? 'Replace API key' : 'API key'}
          </label>
          <div className="relative">
            <KeyRound
              className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
              aria-hidden="true"
            />
            <input
              id={`key-${provider.provider}`}
              // `password` so the browser masks it while typing and keeps it
              // out of autofill history.
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              disabled={anyBusy || !storageAvailable}
              placeholder={storageAvailable ? 'sk-ant-…' : 'Credential storage unavailable'}
              className={cn(
                'ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors',
                'focus:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60',
              )}
            />
          </div>
          <p className="txt-faint text-[11.5px]">
            Saved encrypted, verified against the provider, and never displayed
            again.
          </p>
        </div>

        <button
          type="submit"
          disabled={anyBusy || !storageAvailable || !apiKey.trim()}
          className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--accent)' }}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          ) : (
            <Check className="h-4 w-4" aria-hidden="true" />
          )}
          {provider.configured ? 'Replace & test' : 'Save & test'}
        </button>
      </form>
    </section>
  );
}
