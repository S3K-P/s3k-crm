'use client';

import { apiDownload } from '@/lib/api-client';

/**
 * Hand a fetched file to the browser's download machinery.
 *
 * The anchor is created, clicked and removed in one turn, and the object URL
 * is revoked afterwards. Skipping the revoke keeps the whole blob alive for
 * the lifetime of the tab, which on a CRM export is megabytes per click.
 *
 * `rel="noopener"` is set even though the anchor never reaches the document's
 * link graph: `download` is ignored for cross-origin URLs, and if a future
 * change ever pointed this at one, the opened context must not get a handle on
 * `window.opener`.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * Download an API endpoint's file and save it.
 *
 * The one helper every Export button calls, so the auth-and-save sequence is
 * written once. Errors propagate as `ApiError` for the caller to surface — a
 * 403 from the permission gate and a 413 from the row cap both need to reach
 * the user as a message, not a silently missing file.
 */
export async function downloadAndSave(path: string, fallbackName: string): Promise<void> {
  const { blob, filename } = await apiDownload(path, fallbackName);
  saveBlob(blob, filename);
}
