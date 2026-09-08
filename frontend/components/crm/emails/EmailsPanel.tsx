'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Clock, Loader2, Mail, Paperclip, Plus, Send } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { statusVariant } from '@/components/crm/shared/statusVariants';
import { ListError } from '@/components/crm/shared/ListStates';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import ComposeEmailDrawer from '@/components/crm/emails/ComposeEmailDrawer';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  listEmails,
  sendEmail,
  EMAIL_STATUS_LABEL,
  type EmailMessage,
} from '@/features/crm/emails';
import type { CrmEntityType } from '@/features/crm/tasks';

/* ============================================================
   EMAILS PANEL

   The correspondence on one CRM record, newest first, from
   `GET /crm/emails`. Real data, organization-scoped, and already
   filtered server-side: another user's drafts never arrive here,
   and a blind-copy list arrives only for the person who sent it.

   Fails visibly rather than falling back to sample entries.
   ============================================================ */

function formatWhen(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Who a message went to, shortened when the list is long. */
function describeRecipients(message: EmailMessage): string {
  const shown = message.to_addresses.slice(0, 2).join(', ');
  const extra =
    message.to_addresses.length - 2 + message.cc_addresses.length + message.bcc_count;
  return extra > 0 ? `${shown} +${extra}` : shown;
}

export function EmailsPanel({
  entityType,
  entityId,
  defaultTo,
}: {
  entityType: CrmEntityType;
  entityId: string;
  /** The record's own address, pre-filled into a new message. */
  defaultTo?: string | null;
}) {
  const { can } = usePermissions();
  const mayView = can('emails', 'VIEW');
  const mayCompose = can('emails', 'CREATE');

  const [items, setItems] = useState<EmailMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState(0);
  const [composing, setComposing] = useState(false);
  const [queueing, setQueueing] = useState<string | null>(null);

  const reload = useCallback(() => setToken((n) => n + 1), []);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;

    void (async () => {
      try {
        const result = await listEmails({
          related_entity_type: entityType,
          related_entity_id: entityId,
          page_size: 50,
          sort_by: 'created_at',
          sort_dir: 'desc',
        });
        if (!cancelled) {
          setItems(result.data);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load email.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [entityType, entityId, mayView, token]);

  /**
   * Apply a message the API just returned, instead of re-reading the list.
   *
   * The response is the row the server wrote, returned by the request that
   * wrote it. Re-fetching is a race: the API commits during request teardown,
   * after the response has gone out, so a list request issued the instant a
   * mutation returns can be served on another connection mid-commit and come
   * back describing the row's previous state — leaving a message that was
   * just sent still showing "Draft" on the record.
   */
  const replaceMessage = useCallback((saved: EmailMessage) => {
    setItems((current) =>
      current === null
        ? [saved]
        : current.map((item) => (item.id === saved.id ? saved : item)),
    );
  }, []);

  /** Add a message the API just created. Newest first, matching the sort. */
  const prependMessage = useCallback((saved: EmailMessage) => {
    setItems((current) => (current === null ? [saved] : [saved, ...current]));
  }, []);

  // Every hook is above this early return.
  if (!mayView) return null;

  const handleSend = async (message: EmailMessage) => {
    setQueueing(message.id);
    try {
      const sent = await sendEmail(message.id);
      notifySuccess('Message queued for delivery');
      replaceMessage(sent);
    } catch (caught) {
      notifyError(caught, 'The message could not be queued.');
    } finally {
      setQueueing(null);
    }
  };

  return (
    <div className="surface bd rounded-2xl border p-5">
      <SectionHeader
        title="Email"
        action={
          mayCompose ? (
            <button
              type="button"
              className="btn-secondary inline-flex items-center gap-1.5"
              onClick={() => setComposing(true)}
            >
              <Plus className="h-4 w-4" aria-hidden />
              New email
            </button>
          ) : undefined
        }
      />

      {error && <ListError message={error} onRetry={reload} />}

      {!error && items === null && (
        <div className="txt-muted flex items-center gap-2 py-6 text-[13px]">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading email…
        </div>
      )}

      {!error && items !== null && items.length === 0 && (
        <p className="txt-muted py-6 text-[13px]">No email has been sent to this record yet.</p>
      )}

      {!error && items !== null && items.length > 0 && (
        <ul className="divide-bd divide-y">
          {items.map((message) => (
            <li key={message.id} className="py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Mail className="txt-muted h-3.5 w-3.5 shrink-0" aria-hidden />
                    <p className="txt truncate text-[13.5px] font-semibold">{message.subject}</p>
                    <StatusBadge
                      label={EMAIL_STATUS_LABEL[message.status]}
                      variant={statusVariant(message.status)}
                    />
                  </div>
                  <p className="txt-muted mt-1 truncate text-[12.5px]">
                    To {describeRecipients(message)}
                  </p>
                  {message.attachment_count > 0 && (
                    <p className="txt-muted mt-1 flex items-center gap-1 text-[12px]">
                      <Paperclip className="h-3 w-3" aria-hidden />
                      {message.attachment_count}{' '}
                      {message.attachment_count === 1 ? 'attachment' : 'attachments'}
                    </p>
                  )}
                  {message.status === 'FAILED' && message.error && (
                    /* Shown in full: "failed" with no reason leaves the sender
                       with nothing to do about it. */
                    <p className="mt-1 flex items-start gap-1.5 text-[12px] text-red-600 dark:text-red-400">
                      <AlertTriangle className="mt-[2px] h-3 w-3 shrink-0" aria-hidden />
                      {message.error}
                    </p>
                  )}
                  {message.status === 'QUEUED' && (
                    <p className="txt-muted mt-1 flex items-center gap-1.5 text-[12px]">
                      <Clock className="h-3 w-3" aria-hidden />
                      Waiting to be delivered.
                    </p>
                  )}
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <span className="txt-muted text-[12px]">
                    {formatWhen(message.sent_at ?? message.created_at)}
                  </span>
                  {message.status === 'DRAFT' && mayCompose && (
                    <button
                      type="button"
                      className="btn-ghost inline-flex items-center gap-1.5"
                      // Named per message: a column of buttons all called
                      // "Send" tells a screen-reader user nothing about which
                      // draft they are about to send.
                      aria-label={`Send ${message.subject}`}
                      onClick={() => void handleSend(message)}
                      disabled={queueing === message.id}
                    >
                      {queueing === message.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                      ) : (
                        <Send className="h-3.5 w-3.5" aria-hidden />
                      )}
                      Send
                    </button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ComposeEmailDrawer
        open={composing}
        onClose={() => setComposing(false)}
        entityType={entityType}
        entityId={entityId}
        defaultTo={defaultTo}
        onSent={prependMessage}
      />
    </div>
  );
}

export default EmailsPanel;
