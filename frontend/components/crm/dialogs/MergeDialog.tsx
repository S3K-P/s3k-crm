'use client';

import { useCallback, useEffect, useState } from 'react';
import { GitMerge, Loader2 } from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { FormError } from '@/components/crm/shared/ListStates';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  KEEP_PRIMARY,
  describeMergeValue,
  humanizeField,
  mergeRecords,
  previewMerge,
  type MergeEntity,
  type MergePreview,
} from '@/features/crm/merge';

/* ============================================================
   MERGE DIALOG

   Two steps, because merging is the one operation in the product
   whose mistakes are invisible afterwards.

   1. **Preview.** The server says which fields disagree and how
      much history would move. Nothing has changed yet, and the
      dialog says so.
   2. **Merge.** The choices are sent as *sources* — "keep the
      survivor's" or "take this duplicate's" — never as values.
      A client that could post values could write anything into
      the record under the guise of a merge.

   The confirmation names what moves ("12 activities, 3 notes"),
   because "this cannot be undone" is only a fair warning if the
   user can see what it applies to.
   ============================================================ */

interface MergeDialogProps {
  open: boolean;
  onClose: () => void;
  entity: MergeEntity;
  /** The record that survives. */
  primary: { id: string; label: string };
  /** The records retired into it. */
  duplicates: { id: string; label: string }[];
  /** Called after a successful merge, so the list can reload. */
  onMerged: (survivorId: string) => void;
}

export default function MergeDialog({
  open,
  onClose,
  entity,
  primary,
  duplicates,
  onMerged,
}: MergeDialogProps) {
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [merging, setMerging] = useState(false);

  const duplicateIds = duplicates.map((record) => record.id).join(',');

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    void (async () => {
      try {
        const result = await previewMerge(entity, {
          primary_id: primary.id,
          duplicate_ids: duplicateIds.split(','),
        });
        if (cancelled) return;
        setPreview(result);
        setChoices({});
        setError(null);
      } catch (caught) {
        if (!cancelled) {
          setPreview(null);
          setError(describeApiError(caught, 'The merge could not be previewed.'));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, entity, primary.id, duplicateIds]);

  const labelFor = useCallback(
    (recordId: string) =>
      recordId === primary.id
        ? `${primary.label} (keeping)`
        : (duplicates.find((record) => record.id === recordId)?.label ?? recordId),
    [primary, duplicates],
  );

  const submit = async () => {
    setMerging(true);
    setError(null);
    try {
      const result = await mergeRecords(entity, {
        primary_id: primary.id,
        duplicate_ids: duplicateIds.split(','),
        field_choices: choices,
      });
      notifySuccess(
        'Records merged',
        `${duplicates.length} record${duplicates.length === 1 ? '' : 's'} merged into ${primary.label}.`,
      );
      onMerged(result.id);
      onClose();
    } catch (caught) {
      setError(describeApiError(caught, 'The records could not be merged.'));
      notifyError(caught, 'The records could not be merged.');
    } finally {
      setMerging(false);
    }
  };

  const moving = Object.entries(preview?.related_counts ?? {});

  return (
    <SlideDrawer
      open={open}
      onClose={onClose}
      title="Merge records"
      subtitle={`${duplicates.length + 1} records into "${primary.label}"`}
      width="max-w-2xl"
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={merging || preview === null}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {merging ? (
              <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
            ) : (
              <GitMerge className="h-3.5 w-3.5" />
            )}
            Merge records
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        <FormError message={error} />

        {preview === null && error === null && (
          <Loader2 className="txt-faint h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
        )}

        {preview !== null && (
          <>
            <div className="ctl rounded-lg px-4 py-3 text-[12.5px]">
              <p className="txt font-semibold">
                &ldquo;{primary.label}&rdquo; is kept. The others are retired into it.
              </p>
              <p className="txt-muted mt-1">
                {moving.length === 0
                  ? 'No activities, notes or files hang off the records being retired.'
                  : `${moving
                      .map(([label, count]) => `${count} ${label}`)
                      .join(', ')} will move to the record that is kept.`}
              </p>
              <p className="txt-faint mt-1">
                Nothing is deleted. The retired records keep a pointer to the survivor, so an
                old link still resolves.
              </p>
            </div>

            {preview.conflicts.length === 0 ? (
              <p className="txt-muted text-[13px]">
                The records agree on every field, so there is nothing to choose.
              </p>
            ) : (
              <div className="space-y-4">
                <p className="txt text-[13px] font-semibold">
                  {preview.conflicts.length} field
                  {preview.conflicts.length === 1 ? '' : 's'} differ. Choose which value to
                  keep.
                </p>
                {preview.conflicts.map((conflict) => (
                  <fieldset key={conflict.field} className="bd rounded-lg border p-3">
                    <legend className="txt px-1 text-[12px] font-semibold">
                      {humanizeField(conflict.field)}
                    </legend>
                    <div className="space-y-1.5 pt-1">
                      {Object.entries(conflict.values).map(([recordId, value]) => {
                        const source = recordId === primary.id ? KEEP_PRIMARY : recordId;
                        const chosen =
                          (choices[conflict.field] ?? KEEP_PRIMARY) === source;
                        return (
                          <label
                            key={recordId}
                            className="flex items-start gap-2 text-[12.5px]"
                          >
                            <input
                              type="radio"
                              name={`merge-${conflict.field}`}
                              checked={chosen}
                              onChange={() =>
                                setChoices((current) => ({
                                  ...current,
                                  [conflict.field]: source,
                                }))
                              }
                              className="mt-0.5 h-3.5 w-3.5"
                            />
                            <span>
                              <span className="txt font-medium">
                                {describeMergeValue(value)}
                              </span>
                              <span className="txt-faint block text-[11px]">
                                from {labelFor(recordId)}
                              </span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </SlideDrawer>
  );
}
