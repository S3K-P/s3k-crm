/**
 * Customer email — types and API access.
 *
 * Mirrors `backend/app/products/crm/emails/schemas.py`.
 *
 * Two fields here mean more than they look like.
 *
 * `bcc_addresses` is `string[] | null`, and `null` means **"you may not see
 * this"**, not "there were none". The two are told apart by `bcc_count`, which
 * everybody gets: a colleague reading an account timeline can tell that a
 * message had two blind copies — worth knowing when reading a conversation —
 * without learning who they were. Never render `bcc_addresses?.length` as the
 * count; it is wrong for exactly the readers the rule exists for.
 *
 * `status` is `QUEUED` the moment a send returns, and *not* `SENT`. Nothing is
 * on the wire yet: the request enqueues an outbox event and the worker
 * delivers it a few seconds later. The UI has to say "queued", because
 * claiming otherwise is how a user concludes the product lies to them the
 * first time a relay is down.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';
import type { CrmEntityType } from '@/features/crm/tasks';

export type EmailDirection = 'OUTBOUND' | 'INBOUND';

/** Mirrors `EmailStatus`. There is deliberately no `SENDING`. */
export type EmailStatus = 'DRAFT' | 'QUEUED' | 'SENT' | 'FAILED';

export interface EmailMessage extends RecordMeta {
  thread_id: string;
  direction: EmailDirection;
  status: EmailStatus;

  subject: string;
  body_text: string;
  body_html: string | null;

  from_address: string;
  from_name: string | null;
  reply_to: string | null;
  to_addresses: string[];
  cc_addresses: string[];
  /** `null` when the reader may not see them — see the module comment. */
  bcc_addresses: string[] | null;
  /** How many blind copies there were. Always present, always safe to show. */
  bcc_count: number;

  message_id: string | null;
  in_reply_to: string | null;
  template_id: string | null;

  related_entity_type: CrmEntityType | null;
  related_entity_id: string | null;
  owner_id: string | null;

  sent_at: string | null;
  /** Why the last attempt failed, verbatim. Null unless `status` is `FAILED`. */
  error: string | null;
  provider_message_id: string | null;
  attachment_count: number;
}

export interface EmailThread {
  id: string;
  organization_id: string;
  subject: string;
  related_entity_type: CrmEntityType | null;
  related_entity_id: string | null;
  owner_id: string | null;
  /** Null until the first message in the conversation has actually gone out. */
  last_message_at: string | null;
  /** Sent messages only: one person's unsent draft is not in anybody's count. */
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface EmailThreadDetail extends EmailThread {
  /** Oldest first — a conversation reads forwards. */
  messages: EmailMessage[];
}

export interface EmailComposeInput {
  subject: string;
  body_text: string;
  body_html?: string | null;
  to_addresses: string[];
  cc_addresses?: string[];
  bcc_addresses?: string[];
  reply_to?: string | null;
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
  thread_id?: string | null;
  in_reply_to_message_id?: string | null;
  template_id?: string | null;
  /** `false` saves a draft; `true` composes and queues in one request. */
  send?: boolean;
}

export interface EmailDraftUpdate {
  subject?: string;
  body_text?: string;
  body_html?: string | null;
  to_addresses?: string[];
  cc_addresses?: string[];
  bcc_addresses?: string[];
  reply_to?: string | null;
  template_id?: string | null;
}

export interface EmailListParams extends ListParams {
  thread_id?: string | null;
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
  status?: EmailStatus | null;
  direction?: EmailDirection | null;
}

export interface EmailThreadListParams extends ListParams {
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
}

export const listEmails = (params?: EmailListParams) =>
  api.get<Page<EmailMessage>>(`/crm/emails${toQuery(params)}`);

export const getEmail = (id: string) => api.get<EmailMessage>(`/crm/emails/${id}`);

export const composeEmail = (body: EmailComposeInput) =>
  api.post<EmailMessage>('/crm/emails', body);

export const updateDraft = (id: string, body: EmailDraftUpdate) =>
  api.patch<EmailMessage>(`/crm/emails/${id}`, body);

/** Queues a draft. Returns it on `QUEUED`, not `SENT`. */
export const sendEmail = (id: string) => api.post<EmailMessage>(`/crm/emails/${id}/send`, {});

export const archiveEmail = (id: string) => api.delete<void>(`/crm/emails/${id}`);

export const listEmailThreads = (params?: EmailThreadListParams) =>
  api.get<Page<EmailThread>>(`/crm/emails/threads${toQuery(params)}`);

export const getEmailThread = (id: string) =>
  api.get<EmailThreadDetail>(`/crm/emails/threads/${id}`);

/* --- Templates ---------------------------------------------------------- */

export interface EmailTemplate extends RecordMeta {
  name: string;
  description: string | null;
  subject: string;
  body_text: string;
  body_html: string | null;
  category: string | null;
  /** `false` keeps it to its author, the way a private note works. */
  is_shared: boolean;
  owner_id: string | null;
}

export interface EmailTemplateInput {
  name: string;
  description?: string | null;
  subject: string;
  body_text: string;
  body_html?: string | null;
  category?: string | null;
  is_shared?: boolean;
}

export interface RenderedTemplate {
  subject: string;
  body_text: string;
  body_html: string | null;
  /**
   * Placeholders this record could not fill. They are still visible in the
   * rendered text, deliberately — blanking them produces "Dear ," in a
   * customer's inbox — so the composer warns before anything is sent.
   */
  unresolved: string[];
  /** Every placeholder this record type can fill, for the insert-field menu. */
  available: string[];
}

export const listEmailTemplates = (params?: ListParams) =>
  api.get<Page<EmailTemplate>>(`/crm/email-templates${toQuery(params)}`);

export const getEmailTemplate = (id: string) =>
  api.get<EmailTemplate>(`/crm/email-templates/${id}`);

export const createEmailTemplate = (body: EmailTemplateInput) =>
  api.post<EmailTemplate>('/crm/email-templates', body);

export const updateEmailTemplate = (id: string, body: Partial<EmailTemplateInput>) =>
  api.patch<EmailTemplate>(`/crm/email-templates/${id}`, body);

export const archiveEmailTemplate = (id: string) =>
  api.delete<void>(`/crm/email-templates/${id}`);

export const renderEmailTemplate = (
  id: string,
  body: { related_entity_type?: CrmEntityType | null; related_entity_id?: string | null },
) => api.post<RenderedTemplate>(`/crm/email-templates/${id}/render`, body);

export const listPlaceholders = (relatedEntityType?: CrmEntityType | null) =>
  api.get<string[]>(
    `/crm/email-templates/placeholders${toQuery({ related_entity_type: relatedEntityType })}`,
  );

/** Splits a comma- or semicolon-separated recipient box into addresses. */
export function parseRecipients(raw: string): string[] {
  return raw
    .split(/[,;\s]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

/** How a status reads to a person. `QUEUED` is not "Sent" — see the header. */
export const EMAIL_STATUS_LABEL: Record<EmailStatus, string> = {
  DRAFT: 'Draft',
  QUEUED: 'Queued',
  SENT: 'Sent',
  FAILED: 'Failed',
};
