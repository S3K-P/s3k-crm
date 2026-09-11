'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Building2, Loader2, Plus } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { ListError } from '@/components/crm/shared/ListStates';
import AttachmentsPanel from '@/components/crm/shared/AttachmentsPanel';
import CustomFieldsPanel from '@/components/crm/shared/CustomFieldsPanel';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import EmailsPanel from '@/components/crm/emails/EmailsPanel';
import {
  AccountContactsPanel,
  AccountOpportunitiesPanel,
} from '@/components/crm/shared/RelatedLists';
import AccountSummary from '@/components/crm/accounts/AccountSummary';
import AccountTimeline from '@/components/crm/accounts/AccountTimeline';
import { useRecord } from '@/components/crm/shared/useRecord';
import { usePermissions } from '@/context/AuthContext';
import { getAccount, type Account } from '@/features/crm/accounts';

/* ============================================================
   ACCOUNT 360

   Loads the account named by the route `[id]` from the API. An
   id belonging to another organization returns 404 from the
   backend and is presented here as "not found" — identical to
   an id that never existed, which is what stops the page from
   confirming another tenant's records exist.

   Tabbed rather than one long scroll: Overview carries the
   summary header and the account's own fields, and each related
   record type — contacts, deals, activities, emails, notes,
   files, the unified timeline — gets its own tab so none of them
   have to compete for space or attention.
   ============================================================ */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="txt-muted text-[12px] font-semibold uppercase">{label}</p>
      <p className="txt mt-1 text-[13.5px]">{value || '—'}</p>
    </div>
  );
}

export default function AccountDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;
  const { can } = usePermissions();
  const mayCreateContacts = can('contacts', 'CREATE');
  const mayCreateOpportunities = can('opportunities', 'CREATE');

  const { status, data, error, reload } = useRecord<Account>(getAccount, id, {
    errorMessage: 'Could not load this account.',
  });

  /* Bumped after a contact is promoted to primary, so the summary header's
     figure — read from a separate endpoint — stays in step with the change
     the Contacts tab just made. */
  const [summaryRefreshToken, setSummaryRefreshToken] = useState(0);
  const handlePrimaryChanged = () => {
    setSummaryRefreshToken((n) => n + 1);
    reload();
  };

  if (status === 'loading') {
    return (
      <div className="txt-muted flex items-center gap-2 p-8 text-[13px]">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading account…
      </div>
    );
  }

  if (status === 'missing') {
    return (
      <div className="space-y-4 p-6 lg:p-8">
        <button
          type="button"
          onClick={() => router.push('/accounts')}
          className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
        >
          <ArrowLeft className="h-4 w-4" /> Back to accounts
        </button>
        <div className="surface bd rounded-2xl border p-10 text-center">
          <p className="txt text-[14px] font-semibold">Account not found</p>
          <p className="txt-muted mt-1 text-[12.5px]">
            It may have been archived, owned by someone else, or belong to another
            organization.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error' || data === null) {
    return (
      <div className="p-6 lg:p-8">
        <ListError message={error ?? 'Could not load this account.'} onRetry={reload} />
      </div>
    );
  }

  const account = data;

  const tabs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Company details" />
              <div className="space-y-4 pt-2">
                <Field label="Website" value={account.website} />
                <Field label="Phone" value={account.phone} />
                <Field label="Industry" value={account.industry} />
                <Field label="Company size" value={account.company_size} />
                <Field label="Source" value={account.source} />
              </div>
            </div>

            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Address" />
              <div className="space-y-4 pt-2">
                <Field label="Street" value={account.address_line1} />
                <Field
                  label="City, state"
                  value={[account.city, account.state].filter(Boolean).join(', ') || null}
                />
                <Field label="Postal code" value={account.postal_code} />
                <Field label="Country" value={account.country} />
              </div>
            </div>
          </div>

          {account.description && (
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Description" />
              <p className="txt whitespace-pre-wrap pt-1 text-[13.5px]">{account.description}</p>
            </div>
          )}

          <CustomFieldsPanel entityType="ACCOUNT" values={account.custom_fields} />
        </div>
      ),
    },
    {
      id: 'contacts',
      label: 'Contacts',
      content: (
        <AccountContactsPanel account={account} onPrimaryChanged={handlePrimaryChanged} />
      ),
    },
    {
      id: 'deals',
      label: 'Deals',
      content: <AccountOpportunitiesPanel accountId={account.id} />,
    },
    {
      id: 'activities',
      label: 'Activities',
      content: <ActivityTimelinePanel entityType="ACCOUNT" entityId={account.id} />,
    },
    {
      id: 'emails',
      label: 'Emails',
      content: <EmailsPanel entityType="ACCOUNT" entityId={account.id} />,
    },
    {
      id: 'notes',
      label: 'Notes',
      content: <NotesPanel entityType="ACCOUNT" entityId={account.id} />,
    },
    {
      id: 'files',
      label: 'Files',
      content: <AttachmentsPanel entityType="ACCOUNT" entityId={account.id} />,
    },
    {
      id: 'timeline',
      label: 'Timeline',
      content: <AccountTimeline accountId={account.id} />,
    },
  ];

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <button
        type="button"
        onClick={() => router.push('/accounts')}
        className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to accounts
      </button>

      <div className="flex flex-wrap items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-amber-500 to-orange-500">
          <Building2 className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">{account.name}</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            {account.industry ?? 'No industry recorded'}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StatusBadge label={humanize(account.status)} variant={statusVariant(account.status)} />
        </div>
      </div>

      <AccountSummary accountId={account.id} refreshToken={summaryRefreshToken} />

      {/* Both actions carry this account's id through to the create form, so
          the account it belongs to is already chosen when the drawer opens
          and is saved as the real foreign key — not re-typed. */}
      <div className="flex flex-wrap gap-2">
        {mayCreateContacts && (
          <button
            type="button"
            onClick={() => router.push(`/contacts?account_id=${account.id}`)}
            className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New contact
          </button>
        )}
        {mayCreateOpportunities && (
          <button
            type="button"
            onClick={() => router.push(`/opportunities?account_id=${account.id}`)}
            className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New opportunity
          </button>
        )}
      </div>

      <Tabs tabs={tabs} />
    </div>
  );
}
