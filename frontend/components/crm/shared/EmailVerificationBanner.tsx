'use client';

import { useState } from 'react';
import { Loader2, MailWarning, X } from 'lucide-react';

import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { useAuth } from '@/context/AuthContext';
import { requestEmailVerification } from '@/features/auth/email-verification';

/* ============================================================
   EMAIL VERIFICATION BANNER

   Shown across the CRM while the signed-in user's address is
   unverified. Verification is not a gate — the product works
   either way — so this informs and offers a resend; it never
   blocks a page.

   Dismissal lasts for this page session only. An unverified
   address is a standing fact about the account, and a banner
   that could be hidden for good would be forgotten along with
   the reason for it.
   ============================================================ */

export default function EmailVerificationBanner() {
  const { currentUser, refreshProfile } = useAuth();
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

  const user = currentUser?.user;
  if (!user || user.email_verified_at || dismissed) return null;

  const handleResend = async () => {
    if (sending) return;
    setSending(true);
    try {
      const result = await requestEmailVerification();
      if (result.sent) {
        setSentTo(user.email);
        notifySuccess('Verification email sent', `Check ${user.email} for the link.`);
      } else {
        // Verified in another tab or on another device since this page loaded.
        await refreshProfile();
      }
    } catch (error) {
      notifyError(error, 'Could not send the verification email. Please try again shortly.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      role="region"
      aria-label="Email verification"
      className="bd flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b px-5 py-2 text-[12.5px]"
      style={{ background: 'var(--surface-2)' }}
    >
      <MailWarning className="h-4 w-4 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
      <p className="txt min-w-0 flex-1">
        {sentTo ? (
          <span role="status">
            A new link is on its way to <strong className="font-semibold">{sentTo}</strong>.
          </span>
        ) : (
          <>
            Please confirm your email address,{' '}
            <strong className="font-semibold">{user.email}</strong>, using the link we sent you.
          </>
        )}
      </p>
      <button
        type="button"
        onClick={handleResend}
        disabled={sending}
        className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
        style={{ color: 'var(--accent)' }}
      >
        {sending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
        {sending ? 'Sending…' : sentTo ? 'Send again' : 'Resend link'}
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="txt-faint rounded-md p-1 transition hover:opacity-80"
        aria-label="Hide for now"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
