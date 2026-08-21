'use client';

import { toast } from 'sonner';

import { describeApiError } from '@/features/shared/hooks/useCollection';

/* ============================================================
   NOTIFY

   The one way the CRM tells a user how a mutation went. It
   wraps `sonner`, which is already mounted once in the root
   layout, so nothing here has to render a host.

   Two rules this exists to enforce:

   1. **Every mutation reports its outcome.** Before this, a
      successful save closed a drawer and a failed one showed a
      line of red text buried in a form — an archive from a
      table row said nothing at all either way.
   2. **Failures show what the backend actually said.**
      `describeApiError` unwraps `ApiError` so a 422 with a
      real validation message reaches the user instead of a
      generic "something went wrong". A faked success is never
      an option.
   ============================================================ */

/** Milliseconds a toast stays up. Errors linger: they carry detail to read. */
const SUCCESS_MS = 3500;
const ERROR_MS = 7000;
const WARNING_MS = 5000;

export function notifySuccess(message: string, description?: string): void {
  toast.success(message, { description, duration: SUCCESS_MS });
}

/**
 * Report a failed operation.
 *
 * @param error The caught value. An `ApiError` contributes the backend's own
 *   message; anything else falls back to `fallback`.
 * @param fallback Shown when the cause carries no usable message.
 */
export function notifyError(error: unknown, fallback: string): void {
  toast.error(describeApiError(error, fallback), { duration: ERROR_MS });
}

/** A message that is already human-readable — no unwrapping needed. */
export function notifyErrorMessage(message: string): void {
  toast.error(message, { duration: ERROR_MS });
}

export function notifyWarning(message: string, description?: string): void {
  toast.warning(message, { description, duration: WARNING_MS });
}

export function notifyInfo(message: string, description?: string): void {
  toast(message, { description, duration: SUCCESS_MS });
}
