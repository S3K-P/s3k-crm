'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, Loader2, Mail, Paperclip, Plus, Send, Settings2 } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { statusVariant } from '@/components/crm/shared/statusVariants';
import { ListEmpty, ListError } from '@/components/crm/shared/ListStates';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import ComposeEmailDrawer from '@/components/crm/emails/ComposeEmailDrawer';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  listEmails,
  sendEmail,
  EMAIL_STATUS_LABEL,
  type EmailMessage,
  type EmailStatus,
} from '@/features/crm/emails';

/* ============================================================
   EMAIL

   Everything this organization's people have written to
   customers, from `GET /crm/emails`. Server-filtered: another
   user's drafts never reach this list, and a blind-copy list
   arrives only for whoever sent it.

   Filtering is a query parameter rather than a pass over the
   current page — a client-side filter would leave the result
   count describing a different set than the rows.
   ============================================================ */

const STATUSES: EmailStatus[] = ['DRAFT', 'QUEUED', 'SENT', 'FAILED'];

const ANY_STATUS = { value: '', label: 'All statuses' };

function formatWhen(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function EmailsPage() {
  const { can } = usePermissions();
  const mayView = can('emails', 'VIEW');
  const mayCompose = can('emails', 'CREATE');

  const [items, setItems] = useState<EmailMessage[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState('');
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
          status: (status || null) as EmailStatus | null,
          page_size: 50,
          sort_by: 'created_at',
          sort_dir: 'desc',
        });
        if (!cancelled) {
          setItems(result.data);
          setTotal(result.pagination.total);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load email.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayView, status, token]);

  /**
   * Apply a message the API just returned, instead of re-reading the list.
   *
   * The response *is* the authority: it is the row the server wrote, returned
   * by the request that wrote it. Re-fetching instead is a race — the API
   * commits during request teardown, after the response has gone out, so a
   * list request issued the instant a mutation returns can be served on
   * another connection while that commit is still in flight and come back
   * describing the row's *previous* state. That is observable rather than
   * theoretical: a message sent from this list would keep showing "Draft"
   * until something else refreshed the page.
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
    setTotal((count) => count + 1);
  }, []);

  // Every hook is above this early return: bailing out before one would change
  // the hook order between renders.
  if (!mayView) {
    return (
      <div className="surface bd rounded-2xl border p-8 text-center">
        <p className="txt-muted text-[13.5px]">
          You do not have permission to read this organization&apos;s email.
        </p>
      </div>
    );
  }

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
    <div className="space-y-4">
      <SectionHeader
        title="Email"
        action={
          <div className="flex items-center gap-2">
            <Link href="/email-templates" className="btn-ghost inline-flex items-center gap-1.5">
              <Settings2 className="h-4 w-4" aria-hidden />
              Templates
            </Link>
            {mayCompose && (
              <button
                type="button"
                className="btn-primary inline-flex items-center gap-1.5"
                onClick={() => setComposing(true)}
              >
                <Plus className="h-4 w-4" aria-hidden />
                New email
              </button>
            )}
          </div>
        }
      />

      <div className="flex items-center gap-3">
        <FilterSelect
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          options={[
            ANY_STATUS,
            ...STATUSES.map((value) => ({ value, label: EMAIL_STATUS_LABEL[value] })),
          ]}
        />
        {items !== null && (
          <span className="txt-muted text-[12.5px]">
            {total} {total === 1 ? 'message' : 'messages'}
          </span>
        )}
      </div>

      {error && <ListError message={error} onRetry={reload} />}

      {!error && items === null && (
        <div className="txt-muted flex items-center gap-2 py-10 text-[13px]">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading email…
        </div>
      )}

      {!error && items !== null && items.length === 0 && (
        <ListEmpty
          title="No email yet"
          hint="Messages you write to customers appear here, with what happened to each one."
        />
      )}

      {!error && items !== null && items.length > 0 && (
        <ul className="surface bd divide-bd divide-y rounded-2xl border">
          {items.map((message) => (
            <li key={message.id} className="flex items-start justify-between gap-3 p-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Mail className="txt-muted h-3.5 w-3.5 shrink-0" aria-hidden />
                  <p className="txt truncate text-[13.5px] font-semibold">{message.subject}</p>
                  <StatusBadge
                    label={EMAIL_STATUS_LABEL[message.status]}
                    variant={statusVariant(message.status)}
                  />
                  {message.attachment_count > 0 && (
                    <span className="txt-muted inline-flex items-center gap-1 text-[12px]">
                      <Paperclip className="h-3 w-3" aria-hidden />
                      {message.attachment_count}
                    </span>
                  )}
                </div>
                <p className="txt-muted mt-1 truncate text-[12.5px]">
                  To {message.to_addresses.join(', ')}
                  {message.cc_addresses.length > 0 && ` · Cc ${message.cc_addresses.length}`}
                  {/* The count, never `bcc_addresses?.length` — that is null
                      for exactly the readers who may not see the list. */}
                  {message.bcc_count > 0 && ` · Bcc ${message.bcc_count}`}
                </p>
                {message.status === 'FAILED' && message.error && (
                  <p className="mt-1 flex items-start gap-1.5 text-[12px] text-red-600 dark:text-red-400">
                    <AlertTriangle className="mt-[2px] h-3 w-3 shrink-0" aria-hidden />
                    {message.error}
                  </p>
                )}
              </div>

              <div className="flex shrink-0 items-center gap-3">
                <span className="txt-muted text-[12px]">
                  {formatWhen(message.sent_at ?? message.created_at)}
                </span>
                {message.status === 'DRAFT' && mayCompose && (
                  <button
                    type="button"
                    className="btn-ghost inline-flex items-center gap-1.5"
                    // Named per message: a column of buttons all called "Send"
                    // tells a screen-reader user nothing about which draft
                    // they are about to send.
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
            </li>
          ))}
        </ul>
      )}

      <ComposeEmailDrawer
        open={composing}
        onClose={() => setComposing(false)}
        onSent={prependMessage}
      />
    </div>
  );
}
