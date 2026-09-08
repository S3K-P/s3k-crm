'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertCircle, ArrowLeft, Loader2, Mail, MailCheck } from 'lucide-react';

import AuthCard from '@/components/platform/AuthCard';
import { ApiError, apiRequest } from '@/lib/api-client';
import { LOGIN_PATH } from '@/lib/api-config';

/* ============================================================
   FORGOT PASSWORD

   Asks for an address and shows the same confirmation whatever
   the answer.

   That last part is the whole design. The backend returns 202
   with an empty body whether or not the address has an account,
   so that this page cannot be used to find out which addresses
   are registered here — and this page must not undo that by
   rendering two different screens. There is one success state,
   and the copy says "if that address has an account" rather
   than "check your inbox", because the second would be a claim
   we cannot make.
   ============================================================ */

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    setError(null);
    setSubmitting(true);
    try {
      await apiRequest<void>('/auth/forgot-password', {
        method: 'POST',
        body: { email: email.trim() },
        // Nobody is signed in here, and a 401 from an unauthenticated route
        // must not send the client off to rotate a refresh token it does not
        // have.
        skipRefresh: true,
      });
      setSent(true);
    } catch (caught) {
      // Only a throttle or an outage reaches this branch — "no such account"
      // is a 202 like any other. Surfacing the real message matters for the
      // 429, which tells the user to come back rather than to try harder.
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to send a reset link right now. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (sent) {
    return (
      <AuthCard
        title="Check your email"
        subtitle="If that address has an S3K account, a reset link is on its way."
        footer={
          <Link href={LOGIN_PATH} className="txt-muted hover:txt inline-flex items-center gap-1.5">
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Back to sign in
          </Link>
        }
      >
        <div className="mt-5 space-y-4" role="status">
          <div
            className="flex items-start gap-3 rounded-lg p-3.5"
            style={{ background: 'var(--surface-2, rgba(120,120,140,0.07))' }}
          >
            <MailCheck
              className="mt-0.5 h-4 w-4 shrink-0"
              style={{ color: 'var(--accent)' }}
              aria-hidden="true"
            />
            <p className="txt-muted text-[12.5px] leading-relaxed">
              The link can be used once and expires in an hour. If it does not
              arrive, check your spam folder before asking for another — a new
              request replaces the previous link.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setSent(false);
              setError(null);
            }}
            className="ctl w-full py-2.5 text-[13.5px] font-semibold transition hover:opacity-90"
          >
            Use a different address
          </button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Reset your password"
      subtitle="We will email you a link to choose a new one."
      footer={
        <Link href={LOGIN_PATH} className="txt-muted hover:txt inline-flex items-center gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to sign in
        </Link>
      }
    >
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
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
              className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)] disabled:opacity-60"
              placeholder="you@company.com"
            />
          </div>
        </div>

        {error && (
          <p role="alert" className="flex items-start gap-2 text-[12.5px] font-medium text-red-500">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || email.trim().length === 0}
          className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--accent)' }}
        >
          {submitting && (
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          )}
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
    </AuthCard>
  );
}
