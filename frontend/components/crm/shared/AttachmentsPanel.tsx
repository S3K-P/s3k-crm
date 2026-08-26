'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, FileText, Loader2, Paperclip, Trash2, Upload } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  ACCEPT_ATTRIBUTE,
  MAX_ATTACHMENT_BYTES,
  deleteAttachment,
  formatBytes,
  formatFileKind,
  isStorageUnavailable,
  listAttachments,
  openAttachment,
  uploadAttachment,
  type AttachableEntityType,
  type Attachment,
} from '@/features/crm/attachments';

/* ============================================================
   ATTACHMENTS PANEL

   Files hanging off one CRM record, from
   `GET /api/v1/attachments?entity_type=…&entity_id=…`.

   The upload is three steps and the middle one bypasses this
   application entirely: the browser PUTs the file straight to
   object storage against a pre-signed URL. That is why a
   failed upload has to be cleaned up rather than simply
   reported — `uploadAttachment` handles it.

   Permissions are read twice over, and neither reading is the
   control. `documents.CREATE` / `DELETE` decide which buttons
   render; the backend re-checks them *and* re-checks access to
   the record the file hangs off, so a hidden button is a
   courtesy and a forged request is a 403 or a 404.

   Storage may legitimately be unconfigured in a local
   environment. That reports itself as a 503 and is shown as
   such — the panel says attachments are unavailable rather
   than pretending the record has none.
   ============================================================ */

const PAGE_SIZE = 50;

interface AttachmentsPanelProps {
  entityType: AttachableEntityType;
  entityId: string;
}

export default function AttachmentsPanel({
  entityType,
  entityId,
}: AttachmentsPanelProps) {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayView = can('documents', 'VIEW');
  const mayUpload = can('documents', 'CREATE');
  const mayDelete = can('documents', 'DELETE');

  const [items, setItems] = useState<Attachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const fileInput = useRef<HTMLInputElement | null>(null);

  const reload = useCallback(() => setReloadToken((n) => n + 1), []);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;

    void (async () => {
      try {
        const page = await listAttachments({
          entity_type: entityType,
          entity_id: entityId,
          page_size: PAGE_SIZE,
        });
        if (!cancelled) {
          setItems(page.data);
          setError(null);
          setUnavailable(false);
        }
      } catch (caught) {
        if (cancelled) return;
        setItems([]);
        if (isStorageUnavailable(caught)) {
          setUnavailable(true);
          setError(null);
        } else {
          setUnavailable(false);
          setError(describeApiError(caught, 'Attachments could not be loaded.'));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayView, entityType, entityId, reloadToken]);

  // Reading the trail of who may see what is the backend's job; this only
  // decides whether to render a box the caller would get a 403 from.
  if (!mayView) return null;

  const handleFiles = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;

    if (file.size === 0) {
      notifyError(null, 'That file is empty.');
      return;
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      notifyError(
        null,
        `Files may be at most ${formatBytes(MAX_ATTACHMENT_BYTES)}. ` +
          `"${file.name}" is ${formatBytes(file.size)}.`,
      );
      return;
    }

    setUploading(true);
    try {
      await uploadAttachment(file, { entityType, entityId });
      notifySuccess('File attached', file.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The file could not be attached.');
    } finally {
      setUploading(false);
      // Cleared so re-picking the same file fires `change` again.
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const handleOpen = async (attachment: Attachment) => {
    setBusyId(attachment.id);
    try {
      // A fresh short-lived URL each time, never one cached in the page.
      await openAttachment(attachment.id);
    } catch (caught) {
      notifyError(caught, 'That file could not be opened.');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (attachment: Attachment) => {
    const ok = await confirm({
      title: 'Delete this file?',
      description: (
        <>
          <strong>{attachment.name}</strong> will be removed from this record and
          deleted from storage. This cannot be undone.
        </>
      ),
      confirmLabel: 'Delete file',
      tone: 'danger',
    });
    if (!ok) return;

    setBusyId(attachment.id);
    try {
      await deleteAttachment(attachment.id);
      notifySuccess('File deleted', attachment.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The file could not be deleted.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="surface bd rounded-2xl border p-5">
      <SectionHeader
        title="Files"
        action={
          mayUpload && !unavailable ? (
            <>
              <input
                ref={fileInput}
                type="file"
                accept={ACCEPT_ATTRIBUTE}
                className="hidden"
                onChange={(event) => void handleFiles(event.target.files)}
              />
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                disabled={uploading}
                className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploading ? (
                  <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
                ) : (
                  <Upload className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {uploading ? 'Uploading…' : 'Attach file'}
              </button>
            </>
          ) : null
        }
      />

      <div className="pt-2">
        {unavailable ? (
          <p className="txt-muted py-4 text-[12.5px]">
            File storage is not configured for this environment, so attachments are
            unavailable. This record may still have files attached elsewhere.
          </p>
        ) : error !== null ? (
          <div className="py-4">
            <p role="alert" className="text-[12.5px] font-medium text-red-500">
              {error}
            </p>
            <button
              type="button"
              onClick={reload}
              className="ctl bd mt-2 rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
            >
              Try again
            </button>
          </div>
        ) : items === null ? (
          <p className="txt-muted flex items-center gap-2 py-4 text-[12.5px]">
            <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" /> Loading…
          </p>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Paperclip className="txt-faint h-5 w-5" aria-hidden="true" />
            <p className="txt-muted text-[12.5px]">
              No files attached
              {mayUpload ? '. Attach contracts, proposals or screenshots.' : '.'}
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {items.map((attachment) => {
              const busy = busyId === attachment.id;
              return (
                <li
                  key={attachment.id}
                  className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0"
                >
                  <FileText
                    className="txt-faint h-4 w-4 shrink-0"
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="txt truncate text-[13px] font-medium">
                      {attachment.name}
                    </p>
                    <p className="txt-faint text-[11.5px]">
                      {formatFileKind(attachment.mime_type)} ·{' '}
                      {formatBytes(attachment.size_bytes)}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => void handleOpen(attachment)}
                    disabled={busy}
                    aria-label={`Download ${attachment.name}`}
                    className="ctl txt-muted grid h-7 w-7 shrink-0 place-items-center rounded-lg transition hover:opacity-80 disabled:opacity-40"
                  >
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
                    ) : (
                      <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                  </button>

                  {mayDelete && (
                    <button
                      type="button"
                      onClick={() => void handleDelete(attachment)}
                      disabled={busy}
                      aria-label={`Delete ${attachment.name}`}
                      className="ctl grid h-7 w-7 shrink-0 place-items-center rounded-lg text-red-500 transition hover:opacity-80 disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
