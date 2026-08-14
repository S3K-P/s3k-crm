'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, Loader2, Lock, Mail } from 'lucide-react';

import BrandLogo from '@/components/brand/BrandLogo';
import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import { AUTH_ENABLED, POST_LOGIN_PATH } from '@/lib/api-config';
import { BRAND } from '@/config/site';

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
  const { login, isAuthenticated, loading } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
      await login({ email: email.trim(), password });
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

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{ background: 'var(--bg)' }}
    >
      <div className="w-full max-w-[400px]">
        {/* ── Brand ── */}
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <BrandLogo variant="icon" priority />
          <div>
            <h1 className="font-display txt text-[20px] font-extrabold tracking-tight">
              {BRAND.name}
            </h1>
            <p
              className="text-[9px] font-bold uppercase tracking-[0.16em]"
              style={{ color: 'var(--accent)' }}
            >
              {BRAND.tagline}
            </p>
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-6 shadow-[0_20px_50px_-24px_rgba(50,30,90,0.25)]">
          <h2 className="font-display txt text-[17px] font-bold">Sign in</h2>
          <p className="txt-muted mt-1 text-[13px]">
            Use your S3K account to continue.
          </p>

          {!AUTH_ENABLED && (
            <p
              className="mt-4 rounded-xl border p-3 text-[12.5px] leading-relaxed"
              style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}
            >
              No backend is configured. Set{' '}
              <code className="font-mono">NEXT_PUBLIC_API_BASE_URL</code> to enable
              sign-in; until then the application runs on local demonstration data.
            </p>
          )}

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
                  disabled={submitting || !AUTH_ENABLED}
                  className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
                  placeholder="you@company.com"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="password" className="txt text-[13px] font-semibold">
                Password
              </label>
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
                  disabled={submitting || !AUTH_ENABLED}
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
              disabled={submitting || !AUTH_ENABLED}
              className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {submitting && (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
              )}
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p className="txt-faint mt-5 text-center text-[11.5px]">
          {BRAND.footer}
        </p>
      </div>
    </div>
  );
}
