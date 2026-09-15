'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, KeyRound, Loader2, ShieldCheck, ShieldOff } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import { ListError } from '@/components/crm/shared/ListStates';
import FormField, { FormInput } from '@/components/crm/forms/FormField';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  confirmMfaEnrollment,
  disableMfa,
  enrollMfa,
  getMfaStatus,
} from '@/features/auth/mfa';
import type { MfaEnrollment, MfaStatus } from '@/features/auth/types';

/* ============================================================
   ACCOUNT — SECURITY (Checkpoint 8)

   Self-service two-factor authentication: enroll, confirm,
   disable. Distinct from Admin -> Security, which describes what
   the *deployment* enforces; this page is what *this person's*
   own account has turned on.
   ============================================================ */

type View =
  | { step: 'loading' }
  | { step: 'error'; message: string }
  | { step: 'disabled' }
  | { step: 'enrolling'; enrollment: MfaEnrollment }
  | { step: 'enabled' };

export default function AccountSecurityPage() {
  const [view, setView] = useState<View>({ step: 'loading' });
  const [confirmCode, setConfirmCode] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [copiedRecoveryCodes, setCopiedRecoveryCodes] = useState(false);

  const [disabling, setDisabling] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableError, setDisableError] = useState<string | null>(null);
  const [disableSubmitting, setDisableSubmitting] = useState(false);

  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  // Inline rather than a callback the effect invokes: the initial `loading`
  // state comes from `useState`'s own initializer, so nothing here needs to
  // set it synchronously — only the eventual success or failure does, after
  // the `await`.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const status: MfaStatus = await getMfaStatus();
        if (!cancelled) setView({ step: status.enabled ? 'enabled' : 'disabled' });
      } catch (caught) {
        if (!cancelled) {
          setView({
            step: 'error',
            message: describeApiError(caught, 'Could not load your security settings.'),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const startEnrollment = useCallback(async () => {
    try {
      const enrollment = await enrollMfa();
      setConfirmCode('');
      setView({ step: 'enrolling', enrollment });
    } catch (caught) {
      notifyError(caught, 'Could not start enrollment.');
    }
  }, []);

  const submitConfirm = useCallback(async () => {
    if (view.step !== 'enrolling') return;
    setConfirming(true);
    try {
      await confirmMfaEnrollment(confirmCode.trim());
      notifySuccess('Two-factor authentication is now enabled.');
      setView({ step: 'enabled' });
    } catch (caught) {
      notifyError(caught, 'That code did not verify.');
    } finally {
      setConfirming(false);
    }
  }, [view, confirmCode]);

  const submitDisable = useCallback(async () => {
    setDisableError(null);
    setDisableSubmitting(true);
    try {
      await disableMfa(disablePassword);
      notifySuccess('Two-factor authentication is now disabled.');
      setDisabling(false);
      setDisablePassword('');
      setView({ step: 'disabled' });
    } catch (caught) {
      setDisableError(describeApiError(caught, 'Could not disable it.'));
    } finally {
      setDisableSubmitting(false);
    }
  }, [disablePassword]);

  const copyRecoveryCodes = useCallback((codes: string[]) => {
    void navigator.clipboard.writeText(codes.join('\n')).then(() => {
      setCopiedRecoveryCodes(true);
      setTimeout(() => setCopiedRecoveryCodes(false), 2000);
    });
  }, []);

  const header = (
    <div className="flex items-center gap-3.5">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-emerald-500 to-teal-600">
        <KeyRound className="h-5 w-5 text-white" />
      </div>
      <div>
        <h1 className="font-display txt text-[22px] font-extrabold">Security</h1>
        <p className="txt-muted mt-0.5 text-[13px]">
          Two-factor authentication for your own account.
        </p>
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-2xl space-y-5 p-6 lg:p-8">
      {header}

      {view.step === 'loading' && (
        <div className="txt-muted flex items-center gap-2 py-10 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading…
        </div>
      )}

      {view.step === 'error' && <ListError message={view.message} onRetry={retry} />}

      {view.step === 'disabled' && (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Two-factor authentication" />
          <p className="txt-muted text-[13px] leading-relaxed">
            Not enabled. Add a second step — a 6-digit code from an authenticator app — to
            signing in, on top of your password.
          </p>
          <button
            type="button"
            onClick={() => void startEnrollment()}
            className="mt-4 flex items-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <ShieldCheck className="h-4 w-4" /> Enable two-factor authentication
          </button>
        </div>
      )}

      {view.step === 'enrolling' && (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Set up your authenticator app" />

          <ol className="space-y-4 text-[13px]">
            <li>
              <p className="txt font-semibold">1. Add this account</p>
              <p className="txt-muted mt-1">
                Scan the code below with your authenticator app, or enter it by hand:
              </p>
              <code className="bd surface-2 mt-2 block break-all rounded-lg border px-3 py-2 text-[12px]">
                {view.enrollment.secret}
              </code>
            </li>

            <li>
              <p className="txt font-semibold">2. Save your recovery codes</p>
              <p className="txt-muted mt-1">
                Each works once, for when the app isn&rsquo;t available. Shown only this once —
                store them somewhere safe.
              </p>
              <div className="bd surface-2 mt-2 grid grid-cols-2 gap-x-3 gap-y-1 rounded-lg border px-3 py-2.5 font-mono text-[12px]">
                {view.enrollment.recovery_codes.map((code) => (
                  <span key={code}>{code}</span>
                ))}
              </div>
              <button
                type="button"
                onClick={() => copyRecoveryCodes(view.enrollment.recovery_codes)}
                className="ctl bd mt-2 flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
              >
                {copiedRecoveryCodes ? (
                  <Check className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                {copiedRecoveryCodes ? 'Copied' : 'Copy codes'}
              </button>
            </li>

            <li>
              <p className="txt font-semibold">3. Confirm it works</p>
              <p className="txt-muted mt-1">Enter the current code from the app:</p>
              <div className="mt-2 flex items-center gap-2.5">
                <FormInput
                  value={confirmCode}
                  onChange={(event) => setConfirmCode(event.target.value)}
                  placeholder="123456"
                  className="max-w-[160px]"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => void submitConfirm()}
                  disabled={confirming || confirmCode.trim().length === 0}
                  className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
                  style={{ background: 'var(--accent)' }}
                >
                  {confirming && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
                  Confirm
                </button>
              </div>
            </li>
          </ol>
        </div>
      )}

      {view.step === 'enabled' && (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Two-factor authentication" />
          <p className="flex items-center gap-2 text-[13px] font-medium text-emerald-500">
            <ShieldCheck className="h-4 w-4" /> Enabled — a code is required every time you sign
            in.
          </p>

          {!disabling ? (
            <button
              type="button"
              onClick={() => setDisabling(true)}
              className="bd mt-4 flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-[13px] font-semibold text-red-500 transition hover:opacity-80"
            >
              <ShieldOff className="h-4 w-4" /> Disable
            </button>
          ) : (
            <div className="bd surface-2 mt-4 space-y-3 rounded-xl border p-4">
              <FormField
                label="Current password"
                hint="Confirms it's really you, even from an already-signed-in session."
                error={disableError ?? undefined}
              >
                <FormInput
                  type="password"
                  autoFocus
                  value={disablePassword}
                  onChange={(event) => setDisablePassword(event.target.value)}
                />
              </FormField>
              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => void submitDisable()}
                  disabled={disableSubmitting || disablePassword.length === 0}
                  className="rounded-lg bg-red-500 px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
                >
                  {disableSubmitting ? 'Disabling…' : 'Confirm disable'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDisabling(false);
                    setDisablePassword('');
                    setDisableError(null);
                  }}
                  disabled={disableSubmitting}
                  className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
