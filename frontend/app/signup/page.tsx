'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, Loader2, Lock, Mail, User } from 'lucide-react';

import OnboardingShell from '@/components/platform/OnboardingShell';
import { useAuth } from '@/context/AuthContext';
import { ApiError } from '@/lib/api-client';
import { LOGIN_PATH } from '@/lib/api-config';

/* ============================================================
   SIGN UP — STEP 1: CREATE YOUR S3K ACCOUNT

   Creates the *identity* only. The organization is step 2, and
   the separation is deliberate: somebody arriving from an
   invitation link must be able to create an account and join an
   existing tenant without accidentally founding a second one.

   `?next=` carries that intent through, so an invitee lands back
   on the accept screen rather than on the create-organization
   step.
   ============================================================ */

const MIN_PASSWORD_LENGTH = 12;

export default function SignupPage() {
  return (
    <Suspense fallback={<SignupFallback />}>
      <SignupForm />
    </Suspense>
  );
}

function SignupFallback() {
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: 'var(--bg)' }}
    >
      <Loader2 className="txt-muted h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
    </div>
  );
}

/** Only same-origin paths, for the same reason `/login` checks. */
function safeNext(next: string | null): string | null {
  if (!next) return null;
  if (!next.startsWith('/') || next.startsWith('//')) return null;
  return next;
}

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signup, isAuthenticated, loading } = useAuth();

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const next = safeNext(searchParams.get('next'));
  const destination = next ?? '/signup/organization';

  // Somebody already signed in has no business creating a second account.
  useEffect(() => {
    if (!loading && isAuthenticated) router.replace(destination);
  }, [loading, isAuthenticated, router, destination]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    // Checked here purely so the user is told before a round trip. The server
    // enforces the real policy and will refuse a weak password regardless.
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await signup({
        email: email.trim(),
        password,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });
      router.replace(destination);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to create your account right now. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <OnboardingShell
      step={1}
      title="Create your S3K account"
      subtitle="One account for every S3K application."
      footer={
        <span className="txt-muted">
          Already have an account?{' '}
          <Link
            href={LOGIN_PATH}
            className="font-semibold transition hover:opacity-80"
            style={{ color: 'var(--accent)' }}
          >
            Sign in
          </Link>
        </span>
      }
    >
      <form onSubmit={handleSubmit} className="mt-5 space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            id="first_name"
            label="First name"
            icon={<User className="txt-faint h-4 w-4" aria-hidden="true" />}
          >
            <input
              id="first_name"
              name="first_name"
              autoComplete="given-name"
              required
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              disabled={submitting}
              className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
              placeholder="Ada"
            />
          </Field>

          <Field id="last_name" label="Last name">
            <input
              id="last_name"
              name="last_name"
              autoComplete="family-name"
              required
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              disabled={submitting}
              className="ctl w-full px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
              placeholder="Lovelace"
            />
          </Field>
        </div>

        <Field
          id="email"
          label="Work email"
          icon={<Mail className="txt-faint h-4 w-4" aria-hidden="true" />}
        >
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
        </Field>

        <Field
          id="password"
          label="Password"
          icon={<Lock className="txt-faint h-4 w-4" aria-hidden="true" />}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        >
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
            placeholder="••••••••••••"
          />
        </Field>

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
          {submitting ? 'Creating your account…' : 'Create S3K account'}
        </button>
      </form>
    </OnboardingShell>
  );
}

/** Label + optional leading icon + hint, matching the sign-in form's markup. */
function Field({
  id,
  label,
  icon,
  hint,
  children,
}: {
  id: string;
  label: string;
  icon?: React.ReactNode;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="txt text-[13px] font-semibold">
        {label}
      </label>
      <div className="relative">
        {icon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2">
            {icon}
          </span>
        )}
        {children}
      </div>
      {hint && <p className="txt-faint text-[11.5px]">{hint}</p>}
    </div>
  );
}
