'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, KeyRound, Loader2, Lock, Mail } from 'lucide-react';

import BrandLogo from '@/components/brand/BrandLogo';
import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import { POST_LOGIN_PATH } from '@/lib/api-config';
import { PLATFORM_BRAND } from '@/config/site';

/* ============================================================
   LOGIN
   Uses the existing design tokens and control classes so it
   matches the rest of the application without introducing any
   new styling primitives.
   ============================================================ */

/**
 * Resolve the post-login destination from `?next=`.
 *
 * Only a same-origin **path** is accepted. Anything absolute, protocol-relative
 * (`//evil.test`) or otherwise not starting with a single `/` falls back to the
 * default landing page — otherwise this parameter would be an open redirect,
 * turning the login page into a credible phishing hop.
 */
function safeRedirectTarget(next: string | null): string {
  if (!next) return POST_LOGIN_PATH;
  if (!next.startsWith('/') || next.startsWith('//')) return POST_LOGIN_PATH;
  return next;
}

/**
 * Page shell.
 *
 * `LoginForm` reads `?next=`, and `useSearchParams` opts a route out of static
 * prerendering unless it sits inside a Suspense boundary. Wrapping it here
 * keeps `/login` statically shipped while still honouring the parameter.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginFallback() {
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: 'var(--bg)' }}
    >
      <Loader2
        className="txt-muted h-5 w-5 motion-safe:animate-spin"
        aria-label="Loading sign-in"
      />
    </div>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, verifyMfa, isAuthenticated, loading } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Set once the password verifies but a second factor is still owed —
  // switches the form below to the code-entry step.
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState('');

  const destination = useCallback(
    () => safeRedirectTarget(searchParams.get('next')),
    [searchParams],
  );

  // Someone already signed in has no business on this page.
  useEffect(() => {
    if (!loading && isAuthenticated) router.replace(destination());
  }, [loading, isAuthenticated, router, destination]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    setError(null);
    setSubmitting(true);
    try {
      const outcome = await login({ email: email.trim(), password });
      if (outcome.mfaRequired) {
        setChallengeToken(outcome.challengeToken);
        setPassword('');
        return;
      }
      // Return the user to whatever they were trying to reach.
      router.replace(destination());
    } catch (caught) {
      // The backend returns one message for every credential failure; show it
      // verbatim rather than inventing a more specific one.
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to sign in right now. Please try again.',
      );
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyMfa = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting || !challengeToken) return;

    setError(null);
    setSubmitting(true);
    try {
      await verifyMfa(challengeToken, mfaCode.trim());
      router.replace(destination());
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to verify that code right now. Please try again.',
      );
      setMfaCode('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{ background: 'var(--bg)' }}
    >
      <div className="w-full max-w-[400px]">
        {/* ── Brand ── */}
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <BrandLogo variant="icon" priority label={PLATFORM_BRAND.name} />
          <div>
            <h1 className="font-display txt text-[20px] font-extrabold tracking-tight">
              {PLATFORM_BRAND.name}
            </h1>
            <p
              className="text-[9px] font-bold uppercase tracking-[0.16em]"
              style={{ color: 'var(--accent)' }}
            >
              {PLATFORM_BRAND.tagline}
            </p>
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-6 shadow-[0_20px_50px_-24px_rgba(50,30,90,0.25)]">
          {challengeToken ? (
            <>
              <h2 className="font-display txt text-[17px] font-bold">Enter your code</h2>
              <p className="txt-muted mt-1 text-[13px]">
                Open your authenticator app, or use one of your recovery codes.
              </p>

              <form onSubmit={(event) => void handleVerifyMfa(event)} className="mt-5 space-y-4" noValidate>
                <div className="space-y-1.5">
                  <label htmlFor="mfa-code" className="txt text-[13px] font-semibold">
                    Code
                  </label>
                  <div className="relative">
                    <KeyRound
                      className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
                      aria-hidden="true"
                    />
                    <input
                      id="mfa-code"
                      name="mfa-code"
                      type="text"
                      inputMode="text"
                      autoComplete="one-time-code"
                      autoFocus
                      required
                      value={mfaCode}
                      onChange={(event) => setMfaCode(event.target.value)}
                      disabled={submitting}
                      className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
                      placeholder="123456"
                    />
                  </div>
                </div>

                {error && (
                  <p
                    role="alert"
                    className="flex items-start gap-2 text-[12.5px] font-medium text-red-500"
                  >
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={submitting}
                  className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                  style={{ background: 'var(--accent)' }}
                >
                  {submitting && (
                    <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
                  )}
                  {submitting ? 'Verifying…' : 'Verify'}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setChallengeToken(null);
                    setMfaCode('');
                    setError(null);
                  }}
                  className="txt-muted hover:txt w-full text-center text-[12.5px] font-medium"
                >
                  Back to sign in
                </button>
              </form>
            </>
          ) : (
            <>
              <h2 className="font-display txt text-[17px] font-bold">Sign in</h2>
              <p className="txt-muted mt-1 text-[13px]">
                Use your S3K account to continue.
              </p>

              <form onSubmit={handleSubmit} className="mt-5 space-y-4" noValidate>
            <div className="space-y-1.5">
              <label htmlFor="email" className="txt text-[13px] font-semibold">
                Email
              </label>
              <div className="relative">
                <Mail
                  className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
                  aria-hidden="true"
                />
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={submitting}
                  className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
                  placeholder="you@company.com"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <label htmlFor="password" className="txt text-[13px] font-semibold">
                  Password
                </label>
                {/* Beside the field it applies to, which is where somebody
                    looks the moment they realise they cannot remember it. */}
                <Link
                  href="/forgot-password"
                  className="txt-muted hover:txt text-[12px] font-medium"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Lock
                  className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
                  aria-hidden="true"
                />
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={submitting}
                  className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
                  placeholder="••••••••••••"
                />
              </div>
            </div>

            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 text-[12.5px] font-medium text-red-500"
              >
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {submitting && (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
              )}
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
              </form>
            </>
          )}
        </div>

        <p className="txt-faint mt-5 text-center text-[11.5px]">
          {PLATFORM_BRAND.footer}
        </p>
      </div>
    </div>
  );
}
