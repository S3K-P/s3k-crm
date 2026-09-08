'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, ArrowLeft, Check, KeyRound, Loader2, Lock } from 'lucide-react';

import AuthCard from '@/components/platform/AuthCard';
import { ApiError, apiRequest } from '@/lib/api-client';
import { LOGIN_PATH } from '@/lib/api-config';

/* ============================================================
   RESET PASSWORD

   Redeems the token from `?token=` and sets a new password.

   No session is issued on success and none is asked for here:
   the next screen is the sign-in form, which is what proves the
   new password actually works. Handing back tokens on the
   strength of a link in an inbox would skip that.

   The requirements below mirror `validate_password_policy` in
   the backend, and are shown *before* the user submits rather
   than as a list of failures afterwards. The backend remains
   the authority — this is a courtesy, not a gate.
   ============================================================ */

const MIN_PASSWORD_LENGTH = 12;

interface Rule {
  label: string;
  met: (value: string) => boolean;
}

const RULES: Rule[] = [
  { label: `At least ${MIN_PASSWORD_LENGTH} characters`, met: (v) => v.length >= MIN_PASSWORD_LENGTH },
  { label: 'A lowercase letter', met: (v) => /[a-z]/.test(v) },
  { label: 'An uppercase letter', met: (v) => /[A-Z]/.test(v) },
  { label: 'A digit', met: (v) => /\d/.test(v) },
];

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<ResetFallback />}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetFallback() {
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: 'var(--bg)' }}
    >
      <Loader2 className="txt-muted h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
    </div>
  );
}

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const unmet = RULES.filter((rule) => !rule.met(password));
  const mismatched = confirmation.length > 0 && confirmation !== password;
  const ready = token.length > 0 && unmet.length === 0 && !mismatched && confirmation.length > 0;

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting || !ready) return;

    setError(null);
    setSubmitting(true);
    try {
      await apiRequest<void>('/auth/reset-password', {
        method: 'POST',
        body: { token, new_password: password },
        skipRefresh: true,
      });
      setDone(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to reset your password right now. Please try again.',
      );
      // Cleared on failure: an expired link means starting over, and leaving
      // a chosen password in the fields invites a second identical attempt.
      setPassword('');
      setConfirmation('');
    } finally {
      setSubmitting(false);
    }
  };

  // A link that arrived without its token cannot be recovered from here, so
  // the page says so immediately instead of failing after the user has chosen
  // and typed a password twice.
  if (!token) {
    return (
      <AuthCard
        title="This link is incomplete"
        subtitle="It is missing the part that identifies your request."
        footer={
          <Link href="/forgot-password" className="txt-muted hover:txt">
            Request a new link
          </Link>
        }
      >
        <p className="txt-muted mt-5 text-[12.5px] leading-relaxed">
          Some email clients shorten long links. Try opening the message again
          and copying the whole address, or ask for a new one.
        </p>
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard
        title="Password updated"
        subtitle="Every other session has been signed out."
      >
        <div className="mt-5 space-y-4" role="status">
          <p className="txt-muted text-[12.5px] leading-relaxed">
            If somebody else had access to your account, they no longer do. Sign
            in with your new password to continue.
          </p>
          <button
            type="button"
            onClick={() => router.replace(LOGIN_PATH)}
            className="w-full rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            Go to sign in
          </button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="This link can be used once."
      footer={
        <Link href={LOGIN_PATH} className="txt-muted hover:txt inline-flex items-center gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="mt-5 space-y-4" noValidate>
        <div className="space-y-1.5">
          <label htmlFor="password" className="txt text-[13px] font-semibold">
            New password
          </label>
          <div className="relative">
            <KeyRound
              className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
              aria-hidden="true"
            />
            <input
              id="password"
              name="new-password"
              type="password"
              autoComplete="new-password"
              required
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
              className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
              placeholder="••••••••••••"
            />
          </div>
        </div>

        <ul className="space-y-1" aria-label="Password requirements">
          {RULES.map((rule) => {
            const met = rule.met(password);
            return (
              <li key={rule.label} className="flex items-center gap-2 text-[12px]">
                <Check
                  className="h-3.5 w-3.5 shrink-0"
                  style={{ color: met ? 'var(--accent)' : 'var(--faint)' }}
                  aria-hidden="true"
                />
                <span className={met ? 'txt' : 'txt-faint'}>{rule.label}</span>
                {/* The icon is decorative; this carries the state to a screen
                    reader, which cannot see a colour change. */}
                <span className="sr-only">{met ? '— met' : '— not yet met'}</span>
              </li>
            );
          })}
        </ul>

        <div className="space-y-1.5">
          <label htmlFor="confirmation" className="txt text-[13px] font-semibold">
            Confirm new password
          </label>
          <div className="relative">
            <Lock
              className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
              aria-hidden="true"
            />
            <input
              id="confirmation"
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              disabled={submitting}
              aria-invalid={mismatched}
              className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
              placeholder="••••••••••••"
            />
          </div>
          {mismatched && (
            <p className="text-[12px] font-medium text-red-500">
              The two passwords do not match.
            </p>
          )}
        </div>

        {error && (
          <p role="alert" className="flex items-start gap-2 text-[12.5px] font-medium text-red-500">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !ready}
          className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--accent)' }}
        >
          {submitting && (
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          )}
          {submitting ? 'Updating…' : 'Update password'}
        </button>
      </form>
    </AuthCard>
  );
}
