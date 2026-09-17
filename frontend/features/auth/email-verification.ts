import { apiRequest } from '@/lib/api-client';

/* ============================================================
   EMAIL VERIFICATION

   Two calls, mirroring `/auth/verify-email/*`:

   - `requestEmailVerification` mails the signed-in user a fresh
     link. It takes no address: the backend only ever mails the
     caller's own, so this cannot be pointed at anybody else.
   - `confirmEmailVerification` redeems the token from the link.
     It needs no session — the link is often opened on a phone
     that is not signed in — and grants none.

   The mail itself is sent by the backend worker through
   Microsoft Graph. Nothing about the transport, and no
   credential, is visible from here.
   ============================================================ */

/** `POST /auth/verify-email/request` */
export interface EmailVerificationRequestResult {
  /** `false` only when the address was already verified. */
  sent: boolean;
  email_verified: boolean;
}

export function requestEmailVerification(): Promise<EmailVerificationRequestResult> {
  return apiRequest<EmailVerificationRequestResult>('/auth/verify-email/request', {
    method: 'POST',
  });
}

export function confirmEmailVerification(token: string): Promise<void> {
  return apiRequest<void>('/auth/verify-email/confirm', {
    method: 'POST',
    body: { token },
    skipRefresh: true,
  });
}
