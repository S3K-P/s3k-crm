'use client';

import { useCallback, useState } from 'react';
import { AlertTriangle, Building2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { ApiError } from '@/lib/api-client';
import {
  ACCOUNT_STATUSES,
  createAccount,
  type Account,
  type AccountInput,
} from '@/features/crm/accounts';
import { linkResearchToAccount, type ResearchSessionDetail } from '@/features/ai/market-insights';

/* ============================================================
   ADD TO CRM

   Turns an externally researched company into a CRM account
   (§8).

   Three things it deliberately does not do:

   - It does not create the account itself. It calls the ordinary
     `createAccount` endpoint, so validation, ownership defaults,
     duplicate detection and the audit trail are the same as
     creating an account from the Accounts screen. There is no
     second, laxer path into `crm.accounts`.
   - It does not pre-fill from the AI's findings. Research is an
     intelligence layer, not a data source (§7) — copying an
     unverified industry or revenue figure into the customer
     record is exactly the write this feature must not make. The
     company name comes from what the user typed; the rest is
     theirs to fill in.
   - It does not discard the research. Once the account exists,
     the session is linked to it and the conversation is kept.
   ============================================================ */

export default function AddToCrmDrawer({
  open,
  onClose,
  session,
  onLinked,
}: {
  open: boolean;
  onClose: () => void;
  session: ResearchSessionDetail;
  onLinked: (account: Account) => void;
}) {
  // The parent mounts this component only while the drawer is open, so a fresh
  // open starts from a fresh form — no effect resetting state on `open`.
  const [form, setForm] = useState<AccountInput>({ name: session.company_name });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Set when the API reports a same-named account (decision C03). */
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);

  const update = useCallback(
    <K extends keyof AccountInput>(key: K, value: AccountInput[K]) => {
      setForm((current) => ({ ...current, [key]: value }));
    },
    [],
  );

  const submit = useCallback(
    async (allowDuplicate: boolean) => {
      const name = (form.name ?? '').trim();
      if (name.length === 0) {
        setError('A company name is required.');
        return;
      }

      setSaving(true);
      setError(null);
      try {
        const account = await createAccount({ ...form, name }, allowDuplicate);
        // Link second: an account with no research attached is a recoverable
        // state, whereas a session pointing at an account that was never
        // created is not.
        await linkResearchToAccount(session.id, account.id);
        toast.success(`${account.name} added to CRM — research kept`);
        onLinked(account);
        onClose();
      } catch (caught) {
        if (caught instanceof ApiError && caught.code === 'duplicate_account') {
          // Warned about, not blocked — the existing behaviour of the
          // accounts flow, surfaced here rather than reimplemented.
          setDuplicateWarning(caught.message);
        } else if (caught instanceof ApiError) {
          setError(caught.message);
        } else {
          setError('The account could not be created.');
        }
      } finally {
        setSaving(false);
      }
    },
    [form, session.id, onLinked, onClose],
  );

  return (
    <SlideDrawer
      open={open}
      onClose={onClose}
      title="Add to CRM"
      subtitle={`Create an account for ${session.company_name}`}
      footer={
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="ctl px-4 py-2 text-[13px] font-semibold transition hover:opacity-80 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit(duplicateWarning !== null)}
            disabled={saving}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {saving && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
            {duplicateWarning ? 'Create anyway' : 'Create account'}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <PartialDataNotice>
          Only the company name is carried over. Market Insights is an intelligence layer — it
          never writes researched values into your CRM records, so anything below is yours to
          confirm.
        </PartialDataNotice>

        {duplicateWarning && (
          <p
            className="flex items-start gap-2 rounded-lg border px-3 py-2 text-[12.5px]"
            style={{ borderColor: 'var(--accent)', background: 'var(--accent-soft)' }}
            role="alert"
          >
            <AlertTriangle
              className="mt-0.5 h-3.5 w-3.5 shrink-0"
              style={{ color: 'var(--accent)' }}
              aria-hidden="true"
            />
            <span className="txt">{duplicateWarning}</span>
          </p>
        )}

        {error && (
          <p
            className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-[12.5px] text-red-500"
            role="alert"
          >
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        <FormField label="Company name" htmlFor="mi-account-name" required>
          <FormInput
            id="mi-account-name"
            value={form.name ?? ''}
            maxLength={255}
            onChange={(event) => {
              update('name', event.target.value);
              setDuplicateWarning(null);
            }}
          />
        </FormField>

        <FormField label="Industry" htmlFor="mi-account-industry">
          <FormInput
            id="mi-account-industry"
            value={form.industry ?? ''}
            maxLength={120}
            onChange={(event) => update('industry', event.target.value)}
          />
        </FormField>

        <FormField label="Website" htmlFor="mi-account-website">
          <FormInput
            id="mi-account-website"
            value={form.website ?? ''}
            maxLength={512}
            placeholder="example.com"
            onChange={(event) => update('website', event.target.value)}
          />
        </FormField>

        <FormField label="Status" htmlFor="mi-account-status">
          <FormSelect
            id="mi-account-status"
            value={form.status ?? 'ACTIVE'}
            options={ACCOUNT_STATUSES.map((status) => ({
              value: status,
              label: status.replace('_', ' '),
            }))}
            onChange={(event) =>
              update('status', event.target.value as AccountInput['status'])
            }
          />
        </FormField>

        <FormField
          label="Description"
          htmlFor="mi-account-description"
          hint="Your own notes. The research stays attached to this account either way."
        >
          <FormTextarea
            id="mi-account-description"
            rows={3}
            value={form.description ?? ''}
            onChange={(event) => update('description', event.target.value)}
          />
        </FormField>

        <p className="txt-faint flex items-start gap-1.5 text-[11.5px]">
          <Building2 className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          This research session will be linked to the new account, so it stays in History and
          can be continued.
        </p>
      </div>
    </SlideDrawer>
  );
}
