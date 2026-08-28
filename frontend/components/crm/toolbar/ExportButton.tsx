'use client';

import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';

import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';

/* ============================================================
   EXPORT BUTTON

   One implementation for all four list pages, so the states
   that are easy to skip — in flight, refused, too large — are
   handled the same way everywhere rather than once well and
   three times approximately.

   The button is rendered by the caller only when the caller
   holds EXPORT. That is a courtesy, not the control: the API
   refuses the request regardless, and this component still
   reports that refusal if the two ever disagree.
   ============================================================ */

interface ExportButtonProps {
  /** Runs the download. Rejects with `ApiError` on refusal. */
  onExport: () => Promise<void>;
  /** Plural entity name, used in the confirmation and error messages. */
  entityPlural: string;
  /** How many rows the current filters match, for the confirmation. */
  count?: number;
}

export default function ExportButton({ onExport, entityPlural, count }: ExportButtonProps) {
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      await onExport();
      // Named rather than a bare "Done": on a filtered list the number is the
      // thing a person checks the download against.
      notifySuccess(
        count === undefined
          ? `Your ${entityPlural} export has downloaded.`
          : `Exported ${count} ${count === 1 ? entityPlural.replace(/s$/, '') : entityPlural}.`,
      );
    } catch (error) {
      // `notifyError` unwraps an `ApiError` to the backend's own message,
      // which is what distinguishes "you do not have permission" from "narrow
      // your filters" — the only actionable part of either failure.
      notifyError(error, `Something went wrong exporting ${entityPlural}.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={run}
      disabled={busy}
      aria-busy={busy}
      className="ctl flex items-center gap-2 px-3 py-2 text-[13px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {busy ? (
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
      ) : (
        <Download className="h-4 w-4" aria-hidden="true" />
      )}
      {busy ? 'Exporting…' : 'Export CSV'}
    </button>
  );
}
