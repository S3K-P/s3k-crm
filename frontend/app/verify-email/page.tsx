'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, ArrowLeft, Loader2, MailCheck } from 'lucide-react';

import AuthCard from '@/components/platform/AuthCard';
import { useAuth } from '@/context/AuthContext';
import {
  confirmEmailVerification,
  requestEmailVerification,
} from '@/features/auth/email-verification';
import { ApiError } from '@/lib/api-client';
import { LOGIN_PATH, POST_LOGIN_PATH } from '@/lib/api-config';

/* ============================================================
   VERIFY EMAIL

   Redeems the token from `?token=`.

   **Confirmation is a button, not a page load.** Mail security
   scanners open links to inspect them; redeeming on load would
   let a scanner spend the token before the person ever sees the
   page. A deliberate click is what proves a human with the
   inbox arrived here.

   The link needs no session and grants none. When it is no
   longer valid and the visitor *is* signed in, they can ask for
   a fresh one right here instead of hunting for the banner.
   ============================================================ */

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<VerifyFallback />}>
      <VerifyEmailForm />
    </Suspense>
  );
}

function VerifyFallback() {
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: 'var(--bg)' }}
    >
      <Loader2 className="txt-muted h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
    </div>
  );
}

type Resend = 'idle' | 'sending' | 'sent' | 'failed';

function VerifyEmailForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const { isAuthenticated, refreshProfile } = useAuth();

  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resend, setResend] = useState<Resend>('idle');

  const handleConfirm = async () => {
    if (submitting || !token) return;
    setError(null);
    setSubmitting(true);
    try {
      await confirmEmailVerification(token);
      setDone(true);
      if (isAuthenticated) {
        // The banner reads `email_verified_at` from the profile.
        await refreshProfile().catch(() => undefined);
      }
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to confirm your email address right now. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (resend === 'sending') return;
    setResend('sending');
    try {
      await requestEmailVerification();
      setResend('sent');
    } catch {
      setResend('failed');
    }
  };

  const continueHref = isAuthenticated ? POST_LOGIN_PATH : LOGIN_PATH;

  if (!token) {
    return (
      <AuthCard
        title="This link is incomplete"
        subtitle="It is missing the part that identifies your address."
        footer={
          <Link href={continueHref} className="txt-muted hover:txt">
            {isAuthenticated ? 'Back to S3K' : 'Go to sign in'}
          </Link>
        }
      >
        <p className="txt-muted mt-5 text-[12.5px] leading-relaxed">
          Some email clients shorten long links. Open the message again and copy the whole
          address{isAuthenticated ? ', or ask for a new link from the banner in S3K' : ''}.
        </p>
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard title="Email address confirmed" subtitle="Thank you — nothing else to do.">
        <div className="mt-5 space-y-4" role="status">
          <p className="txt-muted flex items-start gap-2 text-[12.5px] leading-relaxed">
            <MailCheck
              className="mt-0.5 h-4 w-4 shrink-0"
              style={{ color: 'var(--accent)' }}
              aria-hidden="true"
            />
            Your address is verified. Notifications and invitations will reach you there.
          </p>
          <button
            type="button"
            onClick={() => router.replace(continueHref)}
            className="w-full rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            {isAuthenticated ? 'Continue to S3K' : 'Go to sign in'}
          </button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Confirm your email address"
      subtitle="This link can be used once."
      footer={
        <Link href={continueHref} className="txt-muted hover:txt inline-flex items-center gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          {isAuthenticated ? 'Back to S3K' : 'Back to sign in'}
        </Link>
      }
    >
      <div className="mt-5 space-y-4">
        <p className="txt-muted text-[12.5px] leading-relaxed">
          Confirming proves this address belongs to your S3K account. It does not sign you in
          or change anything else.
        </p>

        {error && (
          <div role="alert" className="space-y-2">
            <p className="flex items-start gap-2 text-[12.5px] font-medium text-red-500">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {error}
            </p>
            {isAuthenticated && (
              <div className="text-[12.5px]">
                {resend === 'sent' ? (
                  <p className="txt-muted" role="status">
                    A new link is on its way. Check your inbox.
                  </p>
                ) : (
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={resend === 'sending'}
                    className="font-semibold underline-offset-2 hover:underline disabled:opacity-60"
                    style={{ color: 'var(--accent)' }}
                  >
                    {resend === 'sending' ? 'Sending…' : 'Send me a new link'}
                  </button>
                )}
                {resend === 'failed' && (
                  <p className="mt-1 text-red-500">
                    Could not send a new link. Please try again shortly.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={handleConfirm}
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--accent)' }}
        >
          {submitting && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />}
          {submitting ? 'Confirming…' : 'Confirm my email address'}
        </button>
      </div>
    </AuthCard>
  );
}
