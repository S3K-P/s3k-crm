'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Users, Loader2, GitBranch } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import { useRecord } from '@/components/crm/shared/useRecord';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput } from '@/components/crm/forms/FormField';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import { usePermissions } from '@/context/AuthContext';
import { useMutation } from '@/features/shared/hooks/useCollection';
import {
  LEAD_STATUSES,
  changeLeadStatus,
  convertLead,
  getLead,
  type Lead,
  type LeadStatus,
} from '@/features/crm/leads';

/* ============================================================
   LEAD DETAIL

   Loads the lead named by the route `[id]`.

   Conversion posts to `/crm/leads/{id}/convert`, which creates
   the account, the contact and optionally the opportunity in a
   single database transaction — either all of them exist
   afterwards or none do. The button navigates to the new
   account on success, using the ids the API returns.
   ============================================================ */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="txt-muted text-[12px] font-semibold uppercase">{label}</p>
      <p className="txt mt-1 text-[13.5px]">{value || '—'}</p>
    </div>
  );
}

export default function LeadDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;
  const { can } = usePermissions();
  const mayEdit = can('leads', 'EDIT');

  const { status, data, error, reload } = useRecord<Lead>(getLead, id, {
    errorMessage: 'Could not load this lead.',
  });

  const [convertOpen, setConvertOpen] = useState(false);
  const [dealName, setDealName] = useState('');
  const [dealValue, setDealValue] = useState('');
  const [createOpportunity, setCreateOpportunity] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const { pending, error: convertError, clearError, run } = useMutation();

  if (status === 'loading') {
    return (
      <div className="txt-muted flex items-center gap-2 p-8 text-[13px]">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading lead…
      </div>
    );
  }

  if (status === 'missing') {
    return (
      <div className="space-y-4 p-6 lg:p-8">
        <button
          type="button"
          onClick={() => router.push('/leads')}
          className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
        >
          <ArrowLeft className="h-4 w-4" /> Back to leads
        </button>
        <div className="surface bd rounded-2xl border p-10 text-center">
          <p className="txt text-[14px] font-semibold">Lead not found</p>
          <p className="txt-muted mt-1 text-[12.5px]">
            It may have been archived, or it belongs to another organization.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error' || data === null) {
    return (
      <div className="p-6 lg:p-8">
        <ListError message={error ?? 'Could not load this lead.'} onRetry={reload} />
      </div>
    );
  }

  const lead = data;
  const converted = lead.status === 'CONVERTED';

  const handleStatus = async (next: LeadStatus) => {
    setStatusError(null);
    try {
      await changeLeadStatus(lead.id, next);
      reload();
    } catch (caught) {
      setStatusError(
        caught instanceof Error
          ? caught.message
          : 'That status change is not allowed from the current status.',
      );
    }
  };

  const handleConvert = async () => {
    const result = await run(() =>
      convertLead(lead.id, {
        create_opportunity: createOpportunity,
        opportunity_name: dealName.trim() || null,
        opportunity_value: dealValue || null,
      }),
    );
    if (result === undefined) return;
    setConvertOpen(false);
    router.push(`/accounts/${result.account_id}`);
  };

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <button
        type="button"
        onClick={() => router.push('/leads')}
        className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to leads
      </button>

      <div className="flex flex-wrap items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-emerald-500 to-green-600">
          <Users className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">
            {lead.first_name} {lead.last_name}
          </h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            {lead.company ?? 'No company recorded'}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StatusBadge label={humanize(lead.status)} variant={statusVariant(lead.status)} />
          {mayEdit && !converted && (
            <>
              <FilterSelect
                value={lead.status}
                onChange={(event) => void handleStatus(event.target.value as LeadStatus)}
                aria-label="Change lead status"
                options={LEAD_STATUSES.filter((s) => s !== 'CONVERTED').map((value) => ({
                  value,
                  label: humanize(value),
                }))}
              />
              <button
                type="button"
                onClick={() => {
                  setDealName(`${lead.company ?? lead.first_name} — new opportunity`);
                  clearError();
                  setConvertOpen(true);
                }}
                className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
                style={{ background: 'var(--accent)' }}
              >
                <GitBranch className="h-4 w-4" /> Convert
              </button>
            </>
          )}
        </div>
      </div>

      {statusError && (
        <p role="alert" className="text-[12.5px] font-medium text-red-500">
          {statusError}
        </p>
      )}

      {converted && (
        <div className="surface bd rounded-2xl border p-4">
          <p className="txt text-[13px] font-semibold">This lead has been converted.</p>
          <div className="mt-2 flex flex-wrap gap-3 text-[12.5px] font-semibold">
            {lead.converted_account_id && (
              <button
                type="button"
                onClick={() => router.push(`/accounts/${lead.converted_account_id}`)}
                style={{ color: 'var(--accent)' }}
              >
                View account →
              </button>
            )}
            {lead.converted_contact_id && (
              <button
                type="button"
                onClick={() => router.push(`/contacts/${lead.converted_contact_id}`)}
                style={{ color: 'var(--accent)' }}
              >
                View contact →
              </button>
            )}
            {lead.converted_opportunity_id && (
              <button
                type="button"
                onClick={() =>
                  router.push(`/opportunities/${lead.converted_opportunity_id}`)
                }
                style={{ color: 'var(--accent)' }}
              >
                View opportunity →
              </button>
            )}
          </div>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Contact information" />
          <div className="space-y-4 pt-2">
            <Field label="Email" value={lead.email} />
            <Field label="Phone" value={lead.phone} />
            <Field label="Priority" value={lead.priority ? humanize(lead.priority) : null} />
          </div>
        </div>
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Company" />
          <div className="space-y-4 pt-2">
            <Field label="Company" value={lead.company} />
            <Field label="Industry" value={lead.industry} />
            <Field label="Website" value={lead.website} />
            <Field label="Company size" value={lead.company_size} />
          </div>
        </div>
      </div>

      {lead.notes && (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Notes" />
          <p className="txt whitespace-pre-wrap pt-1 text-[13.5px]">{lead.notes}</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <ActivityTimelinePanel entityType="LEAD" entityId={lead.id} />
        <NotesPanel entityType="LEAD" entityId={lead.id} />
      </div>

      <SlideDrawer
        open={convertOpen}
        onClose={() => setConvertOpen(false)}
        title="Convert lead"
        subtitle="Creates an account and a contact in one transaction."
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setConvertOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleConvert()}
              disabled={pending}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending ? 'Converting…' : 'Convert'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <p className="txt-muted text-[12.5px]">
            A new account is created from{' '}
            <span className="txt font-semibold">{lead.company ?? 'the lead name'}</span>, with{' '}
            <span className="txt font-semibold">
              {lead.first_name} {lead.last_name}
            </span>{' '}
            as its first contact. Only a qualified lead can be converted.
          </p>

          <label className="flex items-center gap-2 text-[13px] font-semibold">
            <input
              type="checkbox"
              checked={createOpportunity}
              onChange={(event) => setCreateOpportunity(event.target.checked)}
            />
            Also create an opportunity
          </label>

          {createOpportunity && (
            <>
              <FormField label="Opportunity name">
                <FormInput
                  value={dealName}
                  onChange={(event) => setDealName(event.target.value)}
                />
              </FormField>
              <FormField label="Deal value">
                <FormInput
                  type="number"
                  min="0"
                  step="0.01"
                  value={dealValue}
                  onChange={(event) => setDealValue(event.target.value)}
                />
              </FormField>
            </>
          )}

          <FormError message={convertError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
