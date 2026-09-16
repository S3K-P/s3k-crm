/**
 * Self-service multi-factor authentication — enroll, confirm, disable.
 *
 * Verifying a *login* challenge is not here: that happens before a session
 * exists, so it lives on `AuthContext.verifyMfa` alongside `login` rather
 * than behind these authenticated calls.
 */

import { api } from '@/lib/api-client';
import type { MfaEnrollment, MfaStatus } from '@/features/auth/types';

export const getMfaStatus = () => api.get<MfaStatus>('/auth/mfa/status');

/** Starts enrollment. Not yet active — see `confirmMfaEnrollment`. */
export const enrollMfa = () => api.post<MfaEnrollment>('/auth/mfa/enroll');

export const confirmMfaEnrollment = (code: string) =>
  api.post<void>('/auth/mfa/enroll/confirm', { code });

export const disableMfa = (currentPassword: string) =>
  api.post<void>('/auth/mfa/disable', { current_password: currentPassword });
