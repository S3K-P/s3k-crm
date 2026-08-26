'use client';

import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ArrowLeft, Contact as ContactIcon, Loader2, Plus } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { ListError } from '@/components/crm/shared/ListStates';
import AttachmentsPanel from '@/components/crm/shared/AttachmentsPanel';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import { ContactOpportunitiesPanel } from '@/components/crm/shared/RelatedLists';
import { useRecord } from '@/components/crm/shared/useRecord';
import { usePermissions } from '@/context/AuthContext';
import { getAccount } from '@/features/crm/accounts';
import { getContact, type Contact } from '@/features/crm/contacts';

/* ============================================================
   CONTACT DETAIL
   Loads the contact named by the route `[id]` from the API.
   ============================================================ */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="txt-muted text-[12px] font-semibold uppercase">{label}</p>
      <p className="txt mt-1 text-[13.5px]">{value || '—'}</p>
    </div>
  );
}

export default function ContactDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;

  const { can } = usePermissions();
  const mayCreateOpportunities = can('opportunities', 'CREATE');

  const { status, data, error, reload } = useRecord<Contact>(getContact, id, {
    errorMessage: 'Could not load this contact.',
  });

  /* Resolve the linked account's name, so the relationship reads as a record
     rather than as the phrase "View account". A failure leaves the link in
     place with generic text: losing the name must not lose the route. */
  const accountId = data?.account_id ?? null;
  const [accountName, setAccountName] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId) return;
    let cancelled = false;
    void (async () => {
      try {
        const account = await getAccount(accountId);
        if (!cancelled) setAccountName(account.name);
      } catch {
        if (!cancelled) setAccountName(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  if (status === 'loading') {
    return (
      <div className="txt-muted flex items-center gap-2 p-8 text-[13px]">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading contact…
      </div>
    );
  }

  if (status === 'missing') {
    return (
      <div className="space-y-4 p-6 lg:p-8">
        <button
          type="button"
          onClick={() => router.push('/contacts')}
          className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
        >
          <ArrowLeft className="h-4 w-4" /> Back to contacts
        </button>
        <div className="surface bd rounded-2xl border p-10 text-center">
          <p className="txt text-[14px] font-semibold">Contact not found</p>
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
        <ListError message={error ?? 'Could not load this contact.'} onRetry={reload} />
      </div>
    );
  }

  const contact = data;

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <button
        type="button"
        onClick={() => router.push('/contacts')}
        className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to contacts
      </button>

      <div className="flex flex-wrap items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-600">
          <ContactIcon className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">{contact.full_name}</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            {contact.job_title ?? 'No job title recorded'}
          </p>
        </div>
        <div className="ml-auto">
          <StatusBadge
            label={humanize(contact.status)}
            variant={statusVariant(contact.status)}
          />
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Contact information" />
          <div className="space-y-4 pt-2">
            <Field label="Email" value={contact.email} />
            <Field label="Phone" value={contact.phone} />
            <Field label="Mobile" value={contact.mobile} />
            <Field label="LinkedIn" value={contact.linkedin_url} />
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Role" />
          <div className="space-y-4 pt-2">
            <Field label="Job title" value={contact.job_title} />
            <Field label="Department" value={contact.department} />
            <div>
              <p className="txt-muted text-[12px] font-semibold uppercase">Account</p>
              {contact.account_id ? (
                <button
                  type="button"
                  onClick={() => router.push(`/accounts/${contact.account_id}`)}
                  className="mt-1 text-left text-[13.5px] font-semibold hover:underline"
                  style={{ color: 'var(--accent)' }}
                >
                  {accountName ?? 'View account'} →
                </button>
              ) : (
                <p className="txt mt-1 text-[13.5px]">—</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* The account and the contact both travel with the link, so the new
          deal opens already attached to each — no re-picking, and both are
          written as the foreign keys the backend validates. */}
      {mayCreateOpportunities && contact.account_id && (
        <div>
          <button
            type="button"
            onClick={() =>
              router.push(
                `/opportunities?account_id=${contact.account_id}&contact_id=${contact.id}`,
              )
            }
            className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New opportunity
          </button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <ContactOpportunitiesPanel contactId={contact.id} />
        <div className="space-y-6">
          <ActivityTimelinePanel entityType="CONTACT" entityId={contact.id} />
          <NotesPanel entityType="CONTACT" entityId={contact.id} />
        <AttachmentsPanel entityType="CONTACT" entityId={contact.id} />
        </div>
      </div>
    </div>
  );
}
