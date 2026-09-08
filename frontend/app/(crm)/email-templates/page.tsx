'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Lock, Plus, Trash2, Users } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { FormInput, FormTextarea } from '@/components/crm/forms/FormField';
import { ListEmpty, ListError, FormError } from '@/components/crm/shared/ListStates';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import {
  archiveEmailTemplate,
  createEmailTemplate,
  listEmailTemplates,
  listPlaceholders,
  updateEmailTemplate,
  type EmailTemplate,
} from '@/features/crm/emails';

/* ============================================================
   EMAIL TEMPLATES

   Reusable subjects and bodies with `{{placeholders}}`.

   The double braces are not decoration. A user's body is
   arbitrary prose — a pasted JSON snippet, a price written
   {1,200} — and single-brace substitution would raise at send
   time on any of them, producing a message that cannot go out
   for a reason the sender cannot act on.

   Shared templates belong to the organization; a private one is
   its author's, the way a private note is, and a colleague's is
   simply not in the list.
   ============================================================ */

interface Draft {
  name: string;
  description: string;
  subject: string;
  body_text: string;
  category: string;
  is_shared: boolean;
}

const EMPTY: Draft = {
  name: '',
  description: '',
  subject: '',
  body_text: '',
  category: '',
  is_shared: true,
};

export default function EmailTemplatesPage() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayView = can('emails', 'VIEW');
  const mayCreate = can('emails', 'CREATE');
  const mayEdit = can('emails', 'EDIT');
  const mayDelete = can('emails', 'DELETE');

  const [items, setItems] = useState<EmailTemplate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState(0);
  const [editing, setEditing] = useState<EmailTemplate | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [open, setOpen] = useState(false);
  const [placeholders, setPlaceholders] = useState<string[]>([]);
  const { pending, error: saveError, run } = useMutation();

  const reload = useCallback(() => setToken((n) => n + 1), []);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;

    void (async () => {
      try {
        const result = await listEmailTemplates({
          page_size: 100,
          sort_by: 'name',
          sort_dir: 'asc',
        });
        if (!cancelled) {
          setItems(result.data);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load templates.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayView, token]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void (async () => {
      try {
        /* Contact fields, because that is the record a template is written
           against most often. The composer resolves against whatever record
           it is actually opened from. */
        const names = await listPlaceholders('CONTACT');
        if (!cancelled) setPlaceholders(names);
      } catch {
        /* The insert-field hint is a convenience; losing it must not stop
           somebody writing a template. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!mayView) {
    return (
      <div className="surface bd rounded-2xl border p-8 text-center">
        <p className="txt-muted text-[13.5px]">
          You do not have permission to read email templates.
        </p>
      </div>
    );
  }

  const startCreate = () => {
    setEditing(null);
    setDraft(EMPTY);
    setOpen(true);
  };

  const startEdit = (template: EmailTemplate) => {
    setEditing(template);
    setDraft({
      name: template.name,
      description: template.description ?? '',
      subject: template.subject,
      body_text: template.body_text,
      category: template.category ?? '',
      is_shared: template.is_shared,
    });
    setOpen(true);
  };

  const handleSave = async () => {
    const body = {
      name: draft.name.trim(),
      description: draft.description.trim() || null,
      subject: draft.subject.trim(),
      body_text: draft.body_text,
      category: draft.category.trim() || null,
      is_shared: draft.is_shared,
    };
    const saved = await run(() =>
      editing ? updateEmailTemplate(editing.id, body) : createEmailTemplate(body),
    );
    if (saved === undefined) return;
    notifySuccess(editing ? 'Template updated' : 'Template saved');
    setOpen(false);
    reload();
  };

  const handleDelete = async (template: EmailTemplate) => {
    const ok = await confirm({
      title: `Retire "${template.name}"?`,
      description:
        'It disappears from the composer. Messages already sent with it keep their history, and the name becomes available again.',
      confirmLabel: 'Retire template',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveEmailTemplate(template.id);
      notifySuccess('Template retired');
      reload();
    } catch (caught) {
      notifyError(caught, 'The template could not be retired.');
    }
  };

  const canSave =
    draft.name.trim().length > 0 &&
    draft.subject.trim().length > 0 &&
    draft.body_text.trim().length > 0;

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Email templates"
        action={
          mayCreate ? (
            <button
              type="button"
              className="btn-primary inline-flex items-center gap-1.5"
              onClick={startCreate}
            >
              <Plus className="h-4 w-4" aria-hidden />
              New template
            </button>
          ) : undefined
        }
      />

      {error && <ListError message={error} onRetry={reload} />}

      {!error && items === null && (
        <div className="txt-muted flex items-center gap-2 py-10 text-[13px]">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading templates…
        </div>
      )}

      {!error && items !== null && items.length === 0 && (
        <ListEmpty
          title="No templates yet"
          hint="Save a message you send often, with placeholders the record fills in."
        />
      )}

      {!error && items !== null && items.length > 0 && (
        <ul className="surface bd divide-bd divide-y rounded-2xl border">
          {items.map((template) => (
            <li key={template.id} className="flex items-start justify-between gap-3 p-4">
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => (mayEdit ? startEdit(template) : undefined)}
              >
                <div className="flex items-center gap-2">
                  <p className="txt truncate text-[13.5px] font-semibold">{template.name}</p>
                  {template.is_shared ? (
                    <span className="txt-muted inline-flex items-center gap-1 text-[12px]">
                      <Users className="h-3 w-3" aria-hidden />
                      Shared
                    </span>
                  ) : (
                    <span className="txt-muted inline-flex items-center gap-1 text-[12px]">
                      <Lock className="h-3 w-3" aria-hidden />
                      Private
                    </span>
                  )}
                  {template.category && (
                    <span className="txt-muted text-[12px]">· {template.category}</span>
                  )}
                </div>
                <p className="txt-muted mt-1 truncate text-[12.5px]">{template.subject}</p>
              </button>

              {mayDelete && (
                <button
                  type="button"
                  className="btn-ghost"
                  aria-label={`Retire ${template.name}`}
                  onClick={() => void handleDelete(template)}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <SlideDrawer
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? 'Edit template' : 'New template'}
        subtitle="Placeholders are written {{like.this}} and filled in from the record."
        width="max-w-2xl"
        footer={
          <div className="flex items-center justify-end gap-2">
            <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSave}
              disabled={pending || !canSave}
            >
              {pending ? 'Saving…' : 'Save template'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          {saveError && <FormError message={saveError} />}

          <div>
            <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="tpl-name">
              Name
            </label>
            <FormInput
              id="tpl-name"
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
          </div>

          <div>
            <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="tpl-category">
              Category
            </label>
            <FormInput
              id="tpl-category"
              value={draft.category}
              placeholder="Outreach, Follow-up…"
              onChange={(event) => setDraft({ ...draft, category: event.target.value })}
            />
          </div>

          <div>
            <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="tpl-subject">
              Subject
            </label>
            <FormInput
              id="tpl-subject"
              value={draft.subject}
              onChange={(event) => setDraft({ ...draft, subject: event.target.value })}
            />
          </div>

          <div>
            <label className="txt-muted text-[12px] font-semibold uppercase" htmlFor="tpl-body">
              Body
            </label>
            <FormTextarea
              id="tpl-body"
              rows={14}
              value={draft.body_text}
              onChange={(event) => setDraft({ ...draft, body_text: event.target.value })}
            />
          </div>

          {placeholders.length > 0 && (
            <div>
              <p className="txt-muted text-[12px] font-semibold uppercase">Available placeholders</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {placeholders.map((name) => (
                  <code key={name} className="ctl bd rounded border px-1.5 py-0.5 text-[11.5px]">
                    {`{{${name}}}`}
                  </code>
                ))}
              </div>
              <p className="txt-muted mt-1 text-[12px]">
                A placeholder the record cannot fill stays visible in the message rather than
                becoming blank, and the composer warns before you send.
              </p>
            </div>
          )}

          <label className="flex items-center gap-2 text-[13px]">
            <input
              type="checkbox"
              checked={draft.is_shared}
              onChange={(event) => setDraft({ ...draft, is_shared: event.target.checked })}
            />
            Share with the whole organization
          </label>
        </div>
      </SlideDrawer>
    </div>
  );
}
