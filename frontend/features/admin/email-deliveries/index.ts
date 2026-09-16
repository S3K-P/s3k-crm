/**
 * Email delivery log — types and API access.
 *
 * Mirrors `backend/app/platform/email/schemas.py` and the query parameters of
 * `GET /api/v1/email-deliveries`.
 *
 * **Read-only, like the audit trail beside it.** Sending is something the
 * product does on its own behalf when a record changes; there is no "send
 * this" route to call, and a resend button would need its own permission and
 * its own rate limit before it could exist safely.
 *
 * **There is no message body here, and there is none in the database either.**
 * Storing one would put a password-reset link — a bearer credential — where
 * administrators can read it, which would turn this screen into a way to take
 * a colleague's account over. The template name and the subject say what was
 * sent without being the thing that was sent.
 *
 * Password resets do not appear here at all: they are addressed to a global
 * identity rather than to this organization, so they carry no tenant and the
 * row-level policy keeps them out of every tenant's view.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page } from '@/features/shared/types/api';

export type EmailDeliveryStatus = 'PENDING' | 'SENT' | 'FAILED' | 'SUPPRESSED';

export interface EmailDelivery {
  id: string;
  to_address: string;
  subject: string;
  /** Which template produced it — `invitation`, `meeting_reminder`, … */
  template: string;
  status: EmailDeliveryStatus;
  /** Which provider took it: `graph` (Microsoft Graph), `console`, `null`. */
  provider: string;
  /** The provider's own handle for the message, for asking them what happened. */
  provider_message_id: string | null;
  /** Why it failed, verbatim. Null unless `status` is `FAILED`. */
  error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface EmailDeliveryListParams extends ListParams {
  status?: EmailDeliveryStatus | null;
  template?: string | null;
  to_address?: string | null;
  sent_from?: string | null;
  sent_to?: string | null;
}

export interface EmailDeliverySummary {
  /** Keyed by status name; every status is present, including the zeroes. */
  counts: Record<string, number>;
  /** Templates this organization has actually sent, for the filter control. */
  templates: string[];
}

export const listEmailDeliveries = (params?: EmailDeliveryListParams) =>
  api.get<Page<EmailDelivery>>(`/email-deliveries${toQuery(params)}`);

export const getEmailDeliverySummary = () =>
  api.get<EmailDeliverySummary>('/email-deliveries/summary');

/* ------------------------------------------------------------------
   Presentation helpers
   ------------------------------------------------------------------ */

/** `meeting_reminder` → `Meeting reminder`. */
/**
 * Names that do not survive being de-underscored into a sentence.
 *
 * `crm_email` would otherwise read "Crm email", and it is also the one entry
 * here that is not a template at all: user-authored mail has no template — the
 * body came from a person — and it appears in this log because an
 * administrator asking "is our mail going out" wants the sales email in that
 * answer too.
 */
const TEMPLATE_LABELS: Record<string, string> = {
  crm_email: 'Customer email',
};

export function templateLabel(template: string): string {
  const known = TEMPLATE_LABELS[template];
  if (known) return known;
  const lower = template.replace(/_/g, ' ').toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/**
 * Badge colour for a delivery state.
 *
 * `PENDING` is a warning rather than a neutral: a message that is still
 * pending minutes after it was requested means the worker is not draining the
 * outbox, and that is worth noticing rather than blending in.
 */
export function statusVariantFor(
  status: EmailDeliveryStatus,
): 'success' | 'danger' | 'warning' | 'neutral' {
  if (status === 'SENT') return 'success';
  if (status === 'FAILED') return 'danger';
  if (status === 'PENDING') return 'warning';
  return 'neutral';
}

/**
 * What the provider name means to somebody reading this screen.
 *
 * `null` and `console` are development providers: nothing left the building.
 * An administrator seeing a green "Sent" against a provider that discards
 * everything would reasonably conclude their invitations arrived, so the name
 * is spelled out rather than shown raw.
 */
export function providerLabel(provider: string): string {
  if (provider === 'null') return 'Not configured';
  if (provider === 'console') return 'Console (development)';
  if (provider === 'graph') return 'Microsoft Graph';
  return provider;
}

/** Whether this provider actually delivers mail to a recipient. */
export function providerDelivers(provider: string): boolean {
  return provider !== 'null' && provider !== 'console';
}
