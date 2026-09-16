'use client';

import { useState } from 'react';
import { Loader2, PencilLine, Trash2, X } from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect } from '@/components/crm/forms/FormField';
import { FormError } from '@/components/crm/shared/ListStates';
import type { BulkOperationResult } from '@/features/shared/types/api';

/* ============================================================
   BULK ACTIONS TOOLBAR (Checkpoint 4)

   Appears once two or more rows are selected. "Bulk edit"
   changes one field at a time across every selected record —
   the common CRM shape, not a multi-field diff form — and
   "Bulk delete" archives them, both through the entity's real
   bulk endpoint (`TenantScopedService.bulk_update`/`bulk_delete`),
   never a client-side loop of single-record calls.

   Every call reports a `BulkOperationResult`: some ids may
   succeed and others fail (permission, visibility, validation,
   a business rule), and this component shows both counts rather
   than a single pass/fail — a partial result is never hidden.
   ============================================================ */

export interface BulkEditableField {
  key: string;
  label: string;
  type?: 'text' | 'number' | 'email' | 'tel' | 'select';
  options?: { value: string; label: string }[];
}

interface BulkActionsToolbarProps {
  count: number;
  onClear: () => void;
  mayEdit: boolean;
  mayDelete: boolean;
  editableFields: BulkEditableField[];
  onBulkUpdate: (values: Record<string, string>) => Promise<BulkOperationResult>;
  onBulkDelete: () => Promise<BulkOperationResult>;
  entityLabelPlural: string;
  /** Extra entity-specific actions — e.g. bulk status/stage change. */
  extraActions?: React.ReactNode;
  onDone: () => void;
}

export default function BulkActionsToolbar({
  count,
  onClear,
  mayEdit,
  mayDelete,
  editableFields,
  onBulkUpdate,
  onBulkDelete,
  entityLabelPlural,
  extraActions,
  onDone,
}: BulkActionsToolbarProps) {
  const confirm = useConfirm();
  const [editOpen, setEditOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    const result = await confirm({
      title: `Delete ${count} ${entityLabelPlural}?`,
      description: 'Records are archived, not erased, and can be restored by an administrator.',
      tone: 'danger',
      confirmLabel: 'Delete',
    });
    if (!result) return;
    setDeleting(true);
    try {
      const outcome = await onBulkDelete();
      reportOutcome(outcome, 'deleted');
      onDone();
    } catch (caught) {
      notifyError(caught, 'The bulk delete could not be started.');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="surface bd flex flex-wrap items-center gap-3 rounded-xl border px-4 py-2.5">
      <span className="txt text-[13px] font-semibold">{count} selected</span>
      {mayEdit && (
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          className="txt-accent flex items-center gap-1.5 text-[12.5px] font-medium"
        >
          <PencilLine className="h-3.5 w-3.5" /> Bulk edit
        </button>
      )}
      {extraActions}
      {mayDelete && (
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={deleting}
          className="flex items-center gap-1.5 text-[12.5px] font-medium text-red-500 disabled:opacity-60"
        >
          {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          Bulk delete
        </button>
      )}
      <button
        type="button"
        onClick={onClear}
        className="txt-muted ml-auto flex items-center gap-1 text-[12.5px]"
      >
        <X className="h-3.5 w-3.5" /> Clear selection
      </button>

      {editOpen && (
        <BulkEditDrawer
          count={count}
          fields={editableFields}
          onClose={() => setEditOpen(false)}
          onSubmit={async (values) => {
            const outcome = await onBulkUpdate(values);
            reportOutcome(outcome, 'updated');
            setEditOpen(false);
            onDone();
          }}
        />
      )}
    </div>
  );
}

function reportOutcome(result: BulkOperationResult, verb: string) {
  if (result.failed.length === 0) {
    notifySuccess(`${result.succeeded.length} record(s) ${verb}.`);
    return;
  }
  if (result.succeeded.length === 0) {
    notifyError(new Error(result.failed[0]?.reason ?? 'Failed'), `No records were ${verb}.`);
    return;
  }
  notifySuccess(
    `${result.succeeded.length} record(s) ${verb}.`,
    `${result.failed.length} could not be changed: ${result.failed
      .slice(0, 3)
      .map((f) => f.reason)
      .join('; ')}${result.failed.length > 3 ? '…' : ''}`,
  );
}

function BulkEditDrawer({
  count,
  fields,
  onClose,
  onSubmit,
}: {
  count: number;
  fields: BulkEditableField[];
  onClose: () => void;
  onSubmit: (values: Record<string, string>) => Promise<void>;
}) {
  const [fieldKey, setFieldKey] = useState(fields[0]?.key ?? '');
  const [value, setValue] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const field = fields.find((f) => f.key === fieldKey);

  async function handleSubmit() {
    setPending(true);
    setError(null);
    try {
      await onSubmit({ [fieldKey]: value });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The bulk update could not be started.');
    } finally {
      setPending(false);
    }
  }

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title={`Bulk edit ${count} records`}
      footer={
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost px-4 py-2 text-[13px]">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={pending || !fieldKey}
            className="btn-primary px-4 py-2 text-[13px] disabled:opacity-60"
          >
            {pending ? 'Applying…' : `Apply to ${count} records`}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <FormError message={error} />
        <FormField label="Field to change">
          <FormSelect
            options={fields.map((f) => ({ value: f.key, label: f.label }))}
            value={fieldKey}
            onChange={(e) => {
              setFieldKey(e.target.value);
              setValue('');
            }}
          />
        </FormField>
        <FormField label="New value">
          {field?.type === 'select' ? (
            <FormSelect
              options={field.options ?? []}
              placeholder="Choose…"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          ) : (
            <FormInput
              type={field?.type ?? 'text'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          )}
        </FormField>
        <p className="txt-faint text-[11.5px]">
          Every selected record is validated and saved independently — a record this value is not
          valid for is reported, not silently skipped, and the rest still apply.
        </p>
      </div>
    </SlideDrawer>
  );
}
