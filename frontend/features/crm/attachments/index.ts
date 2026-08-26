/**
 * Attachments — types, API access and the three-step upload.
 *
 * Mirrors `backend/app/platform/documents/schemas.py`.
 *
 * **The bytes never touch our API.** The browser asks for a pre-signed URL,
 * PUTs the file straight to object storage, then tells the API to confirm
 * (doc 09 "Documents & File Storage"). That is why `uploadAttachment` below is
 * an orchestration rather than a single call, and why the middle step uses a
 * bare `fetch` instead of the API client: the target is a different origin and
 * must not receive our `Authorization` header or organization id.
 *
 * The flow can fail in the middle, so it cleans up after itself. A reservation
 * whose PUT never completed is released through `abandonUpload`, which stops
 * abandoned `PENDING` rows accumulating for every cancelled or failed upload.
 */

import { api, ApiError } from '@/lib/api-client';
import { API_BASE_URL, API_PREFIX } from '@/lib/api-config';
import { toQuery, type ListParams, type Page } from '@/features/shared/types/api';

/** Mirrors `AttachmentStatus`. `PENDING` rows are never listed by the API. */
export type AttachmentStatus = 'PENDING' | 'ACTIVE' | 'QUARANTINED';

/** The CRM records a file may hang off. Matches the backend's `ATTACHABLE`. */
export type AttachableEntityType =
  | 'ACCOUNT'
  | 'CONTACT'
  | 'LEAD'
  | 'OPPORTUNITY'
  | 'CAMPAIGN';

export interface Attachment {
  id: string;
  organization_id: string;
  entity_type: string;
  entity_id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  status: AttachmentStatus;
  checksum: string | null;
  created_at: string;
  updated_at: string;
  created_by_id: string | null;
  // `storage_key` is deliberately absent from the API response.
}

interface UploadTicket {
  attachment: Attachment;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
  expires_at: string;
  confirm_path: string;
}

export interface AttachmentDownload {
  url: string;
  expires_at: string;
  filename: string;
}

export interface AttachmentListParams extends ListParams {
  entity_type: AttachableEntityType;
  entity_id: string;
}

export const listAttachments = (params: AttachmentListParams) =>
  api.get<Page<Attachment>>(`/attachments${toQuery(params)}`);

export const getAttachmentDownload = (id: string) =>
  api.get<AttachmentDownload>(`/attachments/${id}/download-url`);

export const deleteAttachment = (id: string) => api.delete<void>(`/attachments/${id}`);

const abandonUpload = (id: string) => api.delete<void>(`/attachments/${id}/upload`);

/**
 * The maximum the backend accepts (doc 13). Checked here too so an oversized
 * file is refused before a round trip, not because the client is trusted — the
 * backend enforces it three times over, and the signed upload URL caps the
 * transfer regardless of what this file says.
 */
export const MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024;

/**
 * Content types the backend whitelists, for the file picker's `accept` hint.
 *
 * A convenience, not a control: `accept` is trivially bypassed and the server
 * re-checks every one of these. Keeping it in step with the backend list means
 * the picker does not offer files that will be rejected a moment later.
 */
export const ACCEPTED_CONTENT_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'text/plain',
  'text/csv',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/zip',
] as const;

export const ACCEPT_ATTRIBUTE = ACCEPTED_CONTENT_TYPES.join(',');

/**
 * Best-effort content type for a file the browser could not identify.
 *
 * Some browsers report `''` for `.csv` or `.md`. Sending an empty type would
 * be rejected by the whitelist, so a type is inferred from the extension —
 * still only a claim, and still re-checked by the server against both the
 * whitelist and the extension.
 */
const TYPE_BY_EXTENSION: Record<string, string> = {
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  txt: 'text/plain',
  log: 'text/plain',
  md: 'text/plain',
  csv: 'text/csv',
  zip: 'application/zip',
};

export function resolveContentType(file: File): string {
  if (file.type) return file.type;
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  return TYPE_BY_EXTENSION[extension] ?? '';
}

/** Thrown when the direct-to-storage PUT fails. */
export class UploadFailedError extends Error {
  constructor(readonly status: number) {
    super(
      status === 0
        ? 'The file could not be sent to storage. Check your connection and try again.'
        : `Storage rejected the upload (HTTP ${status}).`,
    );
    this.name = 'UploadFailedError';
  }
}

/**
 * Upload one file and return the published attachment.
 *
 * Three steps, and the second is the one that cannot go through `api`:
 *
 * 1. `POST /attachments/upload-url` — validates and reserves.
 * 2. `PUT` to object storage, cross-origin, with no credentials of ours.
 * 3. `POST /attachments/{id}/confirm` — verifies against storage and publishes.
 *
 * If step 2 or 3 fails the reservation is released, so a failed upload leaves
 * nothing behind. That cleanup is itself best-effort: if it fails too, the row
 * stays `PENDING` and remains invisible to every read path, which is the safe
 * end state.
 *
 * @param onProgress Reports 0–1. Reserved for a future `XMLHttpRequest`
 *   implementation; `fetch` cannot report upload progress, so today this is
 *   called only at the boundaries.
 */
export async function uploadAttachment(
  file: File,
  target: { entityType: AttachableEntityType; entityId: string },
  onProgress?: (fraction: number) => void,
): Promise<Attachment> {
  const contentType = resolveContentType(file);

  onProgress?.(0);
  const ticket = await api.post<UploadTicket>('/attachments/upload-url', {
    entity_type: target.entityType,
    entity_id: target.entityId,
    filename: file.name,
    content_type: contentType,
    size_bytes: file.size,
  });

  try {
    // `Content-Length` is a forbidden header name: the browser sets it from the
    // body and ignores any attempt to set it here. It is part of the signature,
    // so it still has to *match* — which it does, because the reservation
    // declared `file.size` and this is the same file.
    const headers = Object.fromEntries(
      Object.entries(ticket.headers).filter(
        ([name]) => name.toLowerCase() !== 'content-length',
      ),
    );

    const response = await fetch(ticket.upload_url, {
      method: ticket.method,
      headers,
      body: file,
      // Explicitly no credentials: this is a different origin, and the
      // pre-signed URL is the only authorization it needs.
      credentials: 'omit',
    });
    if (!response.ok) throw new UploadFailedError(response.status);

    onProgress?.(1);
    return await api.post<Attachment>(`/attachments/${ticket.attachment.id}/confirm`);
  } catch (error) {
    // Release the reservation so it does not linger as a PENDING row.
    // Swallowed on purpose: the original failure is what the user needs to
    // see, and an unreleased PENDING row is invisible anyway.
    try {
      await abandonUpload(ticket.attachment.id);
    } catch {
      /* best effort */
    }
    throw error;
  }
}

/**
 * Open an attachment, fetching a fresh short-lived URL first.
 *
 * The URL is never stored or rendered into the page: it is a bearer credential
 * that works for anyone holding it until it expires, so it is requested at the
 * moment of use and handed straight to the browser.
 */
export async function openAttachment(id: string): Promise<void> {
  const ticket = await getAttachmentDownload(id);
  window.open(ticket.url, '_blank', 'noopener,noreferrer');
}

/* ------------------------------------------------------------------
   Presentation helpers
   ------------------------------------------------------------------ */

/** `1536` → `1.5 KB`. Binary units, matching what file managers show. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

/** A short, human label for a MIME type: `application/pdf` → `PDF`. */
export function formatFileKind(mimeType: string): string {
  const known: Record<string, string> = {
    'application/pdf': 'PDF',
    'text/csv': 'CSV',
    'text/plain': 'Text',
    'application/zip': 'ZIP',
    'application/msword': 'Word',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
    'application/vnd.ms-excel': 'Excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel',
    'application/vnd.ms-powerpoint': 'PowerPoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation':
      'PowerPoint',
  };
  if (known[mimeType]) return known[mimeType];
  if (mimeType.startsWith('image/')) return 'Image';
  return mimeType.split('/').pop()?.toUpperCase() ?? 'File';
}

/** Whether an error means storage is not configured for this deployment. */
export function isStorageUnavailable(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503;
}

/** Absolute URL of the confirm endpoint, for debugging. */
export const attachmentsApiBase = `${API_BASE_URL}${API_PREFIX}/attachments`;
