'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, Building2, Check, Loader2 } from 'lucide-react';

import OnboardingShell from '@/components/platform/OnboardingShell';
import { useAuth } from '@/context/AuthContext';
import { api, ApiError } from '@/lib/api-client';
import type { InvitationPreview } from '@/features/platform/types';

/* ============================================================
   ACCEPT AN INVITATION

   The other way into an organization, and the reason signup and
   tenant creation are separate steps: somebody arriving here
   must join the tenant they were invited to, never found one of
   their own.

   Both routes out of the signed-out state carry `?next=` back to
   this page, so the token survives the detour through sign-in or
   sign-up and the user lands where they started.

   The token is read once and never rendered — it is a
   credential, and putting it in the DOM would leak it into any
   screenshot, session replay or error report of this page.
   ============================================================ */

export default function AcceptInvitationPage() {
  return (
    <Suspense fallback={<Centered>Loading invitation…</Centered>}>
      <AcceptInvitation />
    </Suspense>
  );
}

function AcceptInvitation() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, loading, currentUser, refreshProfile } = useAuth();

  const token = searchParams.get('token');

  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [acceptError, setAcceptError] = useState<string | null>(null);

  // Resolve the token first, so the page can name the organization to somebody
  // who is not signed in yet — "you were invited to Acme, sign in as ada@…".
  useEffect(() => {
    // A missing token is decided during render below, not here: setting state
    // synchronously inside an effect causes a cascading render.
    if (!token) return;
    let cancelled = false;
    const load = async () => {
      try {
        const found = await api.get<InvitationPreview>(
          `/invitations/preview?token=${encodeURIComponent(token)}`,
        );
        if (!cancelled) setPreview(found);
      } catch (caught) {
        if (cancelled) return;
        setPreviewError(
          caught instanceof ApiError
            ? caught.message
            : 'This invitation link is no longer valid.',
        );
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const accept = useCallback(async () => {
    if (!token || accepting) return;
    setAcceptError(null);
    setAccepting(true);
    try {
      await api.post('/invitations/accept', { token });
      // The session is already valid; re-reading the profile is what makes the
      // new membership and its permissions current. No second sign-in.
      await refreshProfile();
      router.replace('/workspace');
    } catch (caught) {
      setAcceptError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to accept this invitation right now.',
      );
    } finally {
      setAccepting(false);
    }
  }, [token, accepting, refreshProfile, router]);

  // Derived, not stored: a link with no token is a property of the URL, and
  // there is nothing to fetch or fail.
  const problem = token
    ? previewError
    : 'This invitation link is missing its token.';

  if (problem) {
    return (
      <OnboardingShell step={1} title="Invitation unavailable">
        <p className="txt-muted mt-3 text-[13px]">{problem}</p>
        <Link
          href="/login"
          className="mt-5 inline-block rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90"
          style={{ background: 'var(--accent)' }}
        >
          Go to sign in
        </Link>
      </OnboardingShell>
    );
  }

  if (!preview || loading) {
    return <Centered>Checking your invitation…</Centered>;
  }

  const next = `/invitations/accept?token=${encodeURIComponent(token ?? '')}`;
  const signedInAs = currentUser?.user.email;
  const addressMatches =
    signedInAs !== undefined &&
    signedInAs.toLowerCase() === preview.email.toLowerCase();

  return (
    <OnboardingShell
      step={2}
      title={`Join ${preview.organization_name}`}
      subtitle={`This invitation was issued to ${preview.email}.`}
    >
      <div
        className="mt-5 flex items-center gap-3 rounded-xl p-4"
        style={{ background: 'var(--accent-soft)' }}
      >
        <Building2 className="h-5 w-5 shrink-0 accent" aria-hidden="true" />
        <div className="min-w-0">
          <p className="txt text-[13.5px] font-semibold">{preview.organization_name}</p>
          <p className="txt-muted text-[12px]">
            You will keep your existing S3K account — this adds the organization to it.
          </p>
        </div>
      </div>

      {/* Not signed in: both paths carry the token back here. */}
      {!isAuthenticated && (
        <div className="mt-5 space-y-2.5">
          <p className="txt-muted text-[13px]">
            Sign in as <span className="txt font-semibold">{preview.email}</span> to accept,
            or create an S3K account with that address.
          </p>
          <Link
            href={`/login?next=${encodeURIComponent(next)}`}
            className="block w-full rounded-lg px-4 py-2.5 text-center text-[13.5px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            Sign in to accept
          </Link>
          <Link
            href={`/signup?next=${encodeURIComponent(next)}`}
            className="bd txt block w-full rounded-lg border px-4 py-2.5 text-center text-[13.5px] font-semibold transition hover:opacity-80"
          >
            Create an S3K account
          </Link>
        </div>
      )}

      {/* Signed in as somebody else — the server refuses this too. */}
      {isAuthenticated && !addressMatches && (
        <div className="mt-5">
          <p
            role="alert"
            className="flex items-start gap-2 text-[12.5px] font-medium text-red-500"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            You are signed in as {signedInAs}. This invitation belongs to{' '}
            {preview.email}.
          </p>
          <Link
            href={`/login?next=${encodeURIComponent(next)}`}
            className="mt-4 block w-full rounded-lg px-4 py-2.5 text-center text-[13.5px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            Sign in as {preview.email}
          </Link>
        </div>
      )}

      {isAuthenticated && addressMatches && (
        <div className="mt-5">
          {acceptError && (
            <p
              role="alert"
              className="mb-3 flex items-start gap-2 text-[12.5px] font-medium text-red-500"
            >
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {acceptError}
            </p>
          )}
          <button
            type="button"
            onClick={accept}
            disabled={accepting}
            className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {accepting ? (
              <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
            ) : (
              <Check className="h-4 w-4" aria-hidden="true" />
            )}
            {accepting ? 'Joining…' : `Join ${preview.organization_name}`}
          </button>
        </div>
      )}
    </OnboardingShell>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ background: 'var(--bg)' }}
    >
      <p className="txt-muted flex items-center gap-2.5 text-[13px] font-medium">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
        {children}
      </p>
    </div>
  );
}
