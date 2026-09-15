'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Paperclip, Send, Save, Sparkles } from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { FormInput, FormTextarea } from '@/components/crm/forms/FormField';
import { FormError } from '@/components/crm/shared/ListStates';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { useMutation } from '@/features/shared/hooks/useCollection';
import {
  composeEmail,
  listEmailTemplates,
  parseRecipients,
  renderEmailTemplate,
  sendEmail,
  type EmailMessage,
  type EmailTemplate,
} from '@/features/crm/emails';
import type { CrmEntityType } from '@/features/crm/tasks';
import { draftEmail, type EmailDraftContent, type EmailDraftTone } from '@/features/ai/ai-insights';
import { describeApiError } from '@/features/shared/hooks/useCollection';

/** The only entity kinds `POST /crm/ai-insights/email-draft` reads context for. */
const AI_DRAFT_SUBJECT_KEY: Partial<Record<CrmEntityType, 'account_id' | 'contact_id' | 'opportunity_id' | 'lead_id'>> = {
  ACCOUNT: 'account_id',
  CONTACT: 'contact_id',
  OPPORTUNITY: 'opportunity_id',
  LEAD: 'lead_id',
};

/* ============================================================
   COMPOSE EMAIL

   Writes a real message through `POST /crm/emails`. Nothing here
   is a mock: the draft is a row, sending enqueues an outbox event
   and the worker delivers it.

   Two things the UI is careful about, both because getting them
   wrong misleads the sender:

   - **"Queued", not "Sent".** The request returns before anything
     reaches a relay. Saying "Sent" would be a claim the product
     cannot back up the first time SMTP is down.
   - **Unresolved placeholders are shown before sending.** A
     template rendered against a record that has no phone number
     leaves `{{record.phone}}` in the body on purpose; the warning
     is what stops it reaching a customer.
   ============================================================ */

interface ComposeEmailDrawerProps {
  open: boolean;
  onClose: () => void;
  /** The record this mail is filed against, if any. */
  entityType?: CrmEntityType | null;
  entityId?: string | null;
  /** Pre-filled recipient — the contact's or lead's address. */
  defaultTo?: string | null;
  /** Continue an existing conversation. */
  threadId?: string | null;
  /** Reply to this message, so it threads in the recipient's client. */
  inReplyToMessageId?: string | null;
  defaultSubject?: string;
  onSent?: (message: EmailMessage) => void;
}

/**
 * Mount guard.
 *
 * The form below holds a message somebody is writing, and every field of it
 * has to be empty the next time the composer opens — a BCC left over from a
 * cancelled message would be a real disclosure rather than a stale-input
 * annoyance. Resetting in an effect is the obvious way to get that and the
 * wrong one: it is a cascading render, React lints against it, and it leaves
 * the drawer briefly showing the previous message's contents.
 *
 * Unmounting instead makes the reset structural. `useState` initialisers run
 * once per mount, so "fresh every time it opens" is the default rather than
 * something an effect has to remember to do for each field — and a field added
 * later cannot be forgotten.
 */
export default function ComposeEmailDrawer(props: ComposeEmailDrawerProps) {
  if (!props.open) return null;
  return <ComposeForm {...props} />;
}

function ComposeForm({
  onClose,
  entityType = null,
  entityId = null,
  defaultTo = null,
  threadId = null,
  inReplyToMessageId = null,
  defaultSubject = '',
  onSent,
}: ComposeEmailDrawerProps) {
  const { pending, error, run } = useMutation();

  const [to, setTo] = useState(defaultTo ?? '');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [showCopies, setShowCopies] = useState(false);
  const [subject, setSubject] = useState(defaultSubject);
  const [body, setBody] = useState('');

  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [templateId, setTemplateId] = useState<string>('');
  const [unresolved, setUnresolved] = useState<string[]>([]);
  const [applying, setApplying] = useState(false);

  const [showAiDraft, setShowAiDraft] = useState(false);
  const [aiInstruction, setAiInstruction] = useState('');
  const [aiTone, setAiTone] = useState<EmailDraftTone>('PROFESSIONAL');
  const [aiDrafting, setAiDrafting] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const aiDraftSubjectKey = entityType ? AI_DRAFT_SUBJECT_KEY[entityType] : undefined;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await listEmailTemplates({ page_size: 100, sort_by: 'name', sort_dir: 'asc' });
        if (!cancelled) setTemplates(result.data);
      } catch {
        /* Templates are an optional convenience. A composer that refuses to
           open because the template list failed is worse than one without
           them, so this failure is deliberately silent. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const applyTemplate = useCallback(
    async (id: string) => {
      setTemplateId(id);
      if (!id) {
        setUnresolved([]);
        return;
      }
      setApplying(true);
      try {
        const rendered = await renderEmailTemplate(id, {
          related_entity_type: entityType,
          related_entity_id: entityId,
        });
        setSubject(rendered.subject);
        setBody(rendered.body_text);
        setUnresolved(rendered.unresolved);
      } catch (caught) {
        notifyError(caught, 'The template could not be applied.');
      } finally {
        setApplying(false);
      }
    },
    [entityType, entityId],
  );

  const generateAiDraft = useCallback(async () => {
    if (!aiDraftSubjectKey || !entityId || !aiInstruction.trim()) return;
    setAiDrafting(true);
    setAiError(null);
    try {
      const generation = await draftEmail({
        [aiDraftSubjectKey]: entityId,
        tone: aiTone,
        instruction: aiInstruction.trim(),
        previous_draft: body.trim() || null,
      });
      const content = generation.content as unknown as EmailDraftContent;
      setSubject(content.subject);
      setBody(content.body);
      setTemplateId('');
      setUnresolved([]);
      setShowAiDraft(false);
      setAiInstruction('');
    } catch (caught) {
      setAiError(describeApiError(caught, 'Could not draft this email.'));
    } finally {
      setAiDrafting(false);
    }
  }, [aiDraftSubjectKey, entityId, aiInstruction, aiTone, body]);

  const compose = (send: boolean) => ({
    subject: subject.trim(),
    body_text: body,
    to_addresses: parseRecipients(to),
    cc_addresses: parseRecipients(cc),
    bcc_addresses: parseRecipients(bcc),
    related_entity_type: entityType,
    related_entity_id: entityId,
    thread_id: threadId,
    in_reply_to_message_id: inReplyToMessageId,
    template_id: templateId || null,
    send,
  });

  const handleSend = async () => {
    const saved = await run(() => composeEmail(compose(true)));
    if (saved === undefined) return;
    notifySuccess('Message queued for delivery');
    onSent?.(saved);
    onClose();
  };

  const handleSaveDraft = async () => {
    const saved = await run(() => composeEmail(compose(false)));
    if (saved === undefined) return;
    notifySuccess('Draft saved');
    onSent?.(saved);
    onClose();
  };

  const recipients = parseRecipients(to);
  const canSend = recipients.length > 0 && subject.trim().length > 0 && body.trim().length > 0;

  return (
    <SlideDrawer
      // Always true here: this component only exists while the drawer is open.
      open
      onClose={onClose}
      title={inReplyToMessageId ? 'Reply' : 'New email'}
      subtitle={
        entityType
          ? 'Filed against this record, and visible on its timeline once sent.'
          : 'Not filed against a record.'
      }
      width="max-w-2xl"
      footer={
        <div className="flex items-center justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose} disabled={pending}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-2"
            onClick={handleSaveDraft}
            disabled={pending || !subject.trim()}
          >
            <Save className="h-4 w-4" aria-hidden />
            Save draft
          </button>
          <button
            type="button"
            className="btn-primary inline-flex items-center gap-2"
            onClick={handleSend}
            disabled={pending || !canSend}
          >
            {pending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Send className="h-4 w-4" aria-hidden />
            )}
            Send
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {error && <FormError message={error} />}

        {templates.length > 0 && (
          <div>
            <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="email-template">
              Template
            </label>
            <select
              id="email-template"
              className="bd surface mt-1 w-full rounded-lg border px-3 py-2 text-[13.5px]"
              value={templateId}
              onChange={(event) => void applyTemplate(event.target.value)}
              disabled={applying}
            >
              <option value="">No template</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {aiDraftSubjectKey && (
          <div className="bd rounded-lg border p-3">
            {!showAiDraft ? (
              <button
                type="button"
                onClick={() => setShowAiDraft(true)}
                className="ctl inline-flex items-center gap-1.5 text-[12.5px] font-semibold hover:opacity-80"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" /> Draft with AI
              </button>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="txt text-[12.5px] font-semibold">Draft with AI</p>
                  <select
                    value={aiTone}
                    onChange={(event) => setAiTone(event.target.value as EmailDraftTone)}
                    className="bd surface rounded-md border px-2 py-1 text-[11.5px]"
                  >
                    <option value="PROFESSIONAL">Professional</option>
                    <option value="FRIENDLY">Friendly</option>
                    <option value="CONCISE">Concise</option>
                    <option value="FORMAL">Formal</option>
                  </select>
                </div>
                <FormTextarea
                  value={aiInstruction}
                  onChange={(event) => setAiInstruction(event.target.value)}
                  rows={2}
                  placeholder="What should this email say or do? e.g. follow up after our last meeting"
                />
                {aiError && <p className="text-[11.5px] text-rose-600">{aiError}</p>}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void generateAiDraft()}
                    disabled={aiDrafting || !aiInstruction.trim()}
                    className="btn-primary inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {aiDrafting && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                    {aiDrafting ? 'Drafting…' : 'Generate'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowAiDraft(false)}
                    className="txt-muted text-[12px] hover:opacity-70"
                  >
                    Cancel
                  </button>
                </div>
                <p className="txt-faint text-[11px]">
                  Never sent automatically — review the draft before pressing Send.
                </p>
              </div>
            )}
          </div>
        )}

        {unresolved.length > 0 && (
          /* Not an error — the message can still be sent. It is a warning
             because the placeholder is *visible* in the body, and sending it
             puts "{{record.phone}}" in a customer's inbox. */
          <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[13px] text-amber-700 dark:text-amber-300">
            This record cannot fill {unresolved.join(', ')}. The placeholder is still in the
            message — edit it before sending.
          </p>
        )}

        <div>
          <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="email-to">
            To
          </label>
          <FormInput
            id="email-to"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            placeholder="name@example.com, another@example.com"
          />
        </div>

        {showCopies ? (
          <>
            <div>
              <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="email-cc">
                Cc
              </label>
              <FormInput id="email-cc" value={cc} onChange={(event) => setCc(event.target.value)} />
            </div>
            <div>
              <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="email-bcc">
                Bcc
              </label>
              <FormInput
                id="email-bcc"
                value={bcc}
                onChange={(event) => setBcc(event.target.value)}
              />
              <p className="txt-muted mt-1 text-[12px]">
                Blind copies are not shown to other recipients, and colleagues see only how many
                there were.
              </p>
            </div>
          </>
        ) : (
          <button
            type="button"
            className="txt-muted text-[13px] underline"
            onClick={() => setShowCopies(true)}
          >
            Add Cc / Bcc
          </button>
        )}

        <div>
          <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="email-subject">
            Subject
          </label>
          <FormInput
            id="email-subject"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
          />
        </div>

        <div>
          <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="email-body">
            Message
          </label>
          <FormTextarea
            id="email-body"
            rows={14}
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
        </div>

        <p className="txt-muted flex items-start gap-2 text-[12px]">
          <Paperclip className="mt-[2px] h-3.5 w-3.5 shrink-0" aria-hidden />
          To attach a file, save this as a draft and add it from the draft — attachments are fixed
          once a message has been sent.
        </p>
      </div>
    </SlideDrawer>
  );
}

/** Queue an already-saved draft. Exported for the drafts list. */
export async function queueDraft(id: string): Promise<EmailMessage | null> {
  try {
    const queued = await sendEmail(id);
    notifySuccess('Message queued for delivery');
    return queued;
  } catch (caught) {
    notifyError(caught, 'The message could not be queued.');
    return null;
  }
}
