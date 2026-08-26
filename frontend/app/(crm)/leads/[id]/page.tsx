'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Users, Loader2, GitBranch } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import AttachmentsPanel from '@/components/crm/shared/AttachmentsPanel';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import { useRecord } from '@/components/crm/shared/useRecord';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect } from '@/components/crm/forms/FormField';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import { useAuth, usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import {
  LEAD_STATUSES,
  changeLeadStatus,
  convertLead,
  getLead,
  getLeadConversionSuggestions,
  type Lead,
  type LeadConversionResult,
  type LeadConversionSuggestions,
  type LeadStatus,
} from '@/features/crm/leads';
import { listAccounts, type Account } from '@/features/crm/accounts';
import { listContacts, type Contact } from '@/features/crm/contacts';
import { listStages, type PipelineStage } from '@/features/crm/opportunities';
import { listLeadSources, type LeadSource } from '@/features/crm/lead-sources';
import { listMembers, type OrganizationMember } from '@/features/admin/users';

/* ============================================================
   LEAD DETAIL

   Loads the lead named by the route `[id]`.

   Conversion posts to `/crm/leads/{id}/convert`, which creates
   or links the account and contact and optionally the
   opportunity in a single database transaction. The convert
   drawer loads matching suggestions so reps can attach to
   existing records instead of recreating them.
   ============================================================ */

type AccountMode = 'create' | 'link';
type ContactMode = 'create' | 'link';

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
  const confirm = useConfirm();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;
  const { currentUser } = useAuth();
  const signedInUserId = currentUser?.user.id ?? null;
  const { can } = usePermissions();
  const mayEdit = can('leads', 'EDIT');
  const mayViewAccounts = can('accounts', 'VIEW');
  const mayViewContacts = can('contacts', 'VIEW');
  const mayViewOpportunities = can('opportunities', 'VIEW');
  const mayViewSources = can('lead_sources', 'VIEW');
  const mayViewMembers = can('users', 'VIEW');

  const { status, data, error, reload } = useRecord<Lead>(getLead, id, {
    errorMessage: 'Could not load this lead.',
  });

  const [convertOpen, setConvertOpen] = useState(false);
  const [conversionSuccess, setConversionSuccess] = useState<LeadConversionResult | null>(
    null,
  );
  const [dealName, setDealName] = useState('');
  const [dealValue, setDealValue] = useState('');
  const [stageId, setStageId] = useState('');
  const [closeDate, setCloseDate] = useState('');
  const [createOpportunity, setCreateOpportunity] = useState(true);
  const [accountMode, setAccountMode] = useState<AccountMode>('create');
  const [contactMode, setContactMode] = useState<ContactMode>('create');
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [selectedContactId, setSelectedContactId] = useState('');
  const [suggestions, setSuggestions] = useState<LeadConversionSuggestions | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountContacts, setAccountContacts] = useState<Contact[]>([]);
  const [convertLoading, setConvertLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const { pending, error: convertError, clearError, run } = useMutation();

  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [sources, setSources] = useState<LeadSource[]>([]);
  const [members, setMembers] = useState<OrganizationMember[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (mayViewSources) {
        try {
          const page = await listLeadSources({ page_size: 200 });
          if (!cancelled) setSources(page.data);
        } catch {
          /* non-fatal */
        }
      }
      if (mayViewMembers) {
        try {
          const page = await listMembers();
          if (!cancelled) setMembers(page.data);
        } catch {
          /* non-fatal */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewMembers, mayViewSources]);

  useEffect(() => {
    if (!convertOpen || !id) return;
    let cancelled = false;
    void (async () => {
      setConvertLoading(true);
      try {
        const jobs: Promise<void>[] = [
          getLeadConversionSuggestions(id)
            .then((loaded) => {
              if (cancelled) return;
              setSuggestions(loaded);
              setDealName(loaded.suggested_opportunity_name);
              setDealValue(loaded.suggested_deal_value ?? '');
              // Prefer linking when exact matches already exist.
              if (loaded.matching_accounts.length > 0) {
                setAccountMode('link');
                setSelectedAccountId(loaded.matching_accounts[0]!.id);
              } else {
                setAccountMode('create');
                setSelectedAccountId('');
              }
              if (loaded.matching_contacts.length > 0) {
                setContactMode('link');
                setSelectedContactId(loaded.matching_contacts[0]!.id);
              } else {
                setContactMode('create');
                setSelectedContactId('');
              }
            })
            .catch(() => {
              if (!cancelled) setSuggestions(null);
            }),
        ];

        if (mayViewOpportunities) {
          jobs.push(
            listStages()
              .then((loaded) => {
                if (!cancelled) {
                  setStages(loaded.filter((stage) => !stage.is_won && !stage.is_lost));
                }
              })
              .catch(() => undefined),
          );
        }

        if (mayViewAccounts) {
          jobs.push(
            listAccounts({ page_size: 200, sort_by: 'name', sort_dir: 'asc' })
              .then((page) => {
                if (!cancelled) setAccounts(page.data);
              })
              .catch(() => undefined),
          );
        }

        await Promise.all(jobs);
      } finally {
        if (!cancelled) setConvertLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [convertOpen, id, mayViewAccounts, mayViewOpportunities]);

  /* Contacts for the account being linked — so the contact picker stays in sync. */
  const linkedAccountId =
    accountMode === 'link' ? selectedAccountId : null;

  useEffect(() => {
    if (!convertOpen || !mayViewContacts || !linkedAccountId) {
      setAccountContacts([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const page = await listContacts({
          account_id: linkedAccountId,
          page_size: 100,
          sort_by: 'last_name',
          sort_dir: 'asc',
        });
        if (!cancelled) setAccountContacts(page.data);
      } catch {
        if (!cancelled) setAccountContacts([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [convertOpen, mayViewContacts, linkedAccountId]);

  const accountOptions = useMemo(() => {
    const matchingIds = new Set(
      (suggestions?.matching_accounts ?? []).map((account) => account.id),
    );
    const matching = (suggestions?.matching_accounts ?? []).map((account) => ({
      value: account.id,
      label: `${account.name} (match)`,
    }));
    const rest = accounts
      .filter((account) => !matchingIds.has(account.id))
      .map((account) => ({ value: account.id, label: account.name }));
    return [...matching, ...rest];
  }, [accounts, suggestions]);

  const contactOptions = useMemo(() => {
    const matching = suggestions?.matching_contacts ?? [];
    const matchingIds = new Set(matching.map((contact) => contact.id));
    // When linking an account, prefer contacts on that account; still surface
    // email/name matches even if they sit elsewhere (backend will re-home them).
    const filteredMatching =
      accountMode === 'link' && selectedAccountId
        ? matching.filter(
            (contact) =>
              contact.account_id === null || contact.account_id === selectedAccountId,
          )
        : matching;
    const fromMatches = filteredMatching.map((contact) => ({
      value: contact.id,
      label: contact.email
        ? `${contact.full_name} <${contact.email}> (match)`
        : `${contact.full_name} (match)`,
    }));
    const fromAccount = accountContacts
      .filter((contact) => !matchingIds.has(contact.id))
      .map((contact) => ({
        value: contact.id,
        label: contact.email
          ? `${contact.full_name} <${contact.email}>`
          : contact.full_name,
      }));
    return [...fromMatches, ...fromAccount];
  }, [accountContacts, accountMode, selectedAccountId, suggestions]);

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
        <ListError message={error ?? 'Could not load this lead.'} onRetry={reload} />
      </div>
    );
  }

  const lead = data;
  const leadName = [lead.first_name, lead.last_name].filter(Boolean).join(' ').trim();
  const converted = lead.status === 'CONVERTED';

  const handleStatus = async (next: LeadStatus) => {
    setStatusError(null);
    /* LOST and UNQUALIFIED take the lead out of the working pipeline, so both
       are confirmed and both capture the reason the backend stores on the
       record. Every other move is a routine step forward. */
    if (next === 'LOST' || next === 'UNQUALIFIED') {
      const answer = await confirm({
        title: next === 'LOST' ? `Mark ${leadName} as lost?` : `Disqualify ${leadName}?`,
        description:
          'The lead leaves the active pipeline and can no longer be converted until it is re-opened as Contacted.',
        confirmLabel: next === 'LOST' ? 'Mark as lost' : 'Disqualify',
        tone: 'danger',
        prompt: {
          label: 'Reason',
          required: true,
          placeholder: 'No budget this year, no decision maker identified…',
          hint: 'Stored on the lead so the pipeline drop-off is explainable later.',
        },
      });
      if (!answer) return;
      try {
        await changeLeadStatus(lead.id, next, answer.value);
        notifySuccess(next === 'LOST' ? 'Lead marked as lost' : 'Lead disqualified');
        reload();
      } catch (caught) {
        setStatusError(describeApiError(caught, 'That status change was rejected.'));
        notifyError(caught, 'That status change was rejected.');
      }
      return;
    }

    try {
      await changeLeadStatus(lead.id, next);
      notifySuccess('Status updated', humanize(next));
      reload();
    } catch (caught) {
      setStatusError(
        describeApiError(
          caught,
          'That status change is not allowed from the current status.',
        ),
      );
      notifyError(caught, 'That status change is not allowed from the current status.');
    }
  };

  const openConvert = () => {
    setCreateOpportunity(true);
    setStageId('');
    setCloseDate('');
    setDealName('');
    setDealValue('');
    setAccountMode('create');
    setContactMode('create');
    setSelectedAccountId('');
    setSelectedContactId('');
    setSuggestions(null);
    setConversionSuccess(null);
    clearError();
    setConvertOpen(true);
  };

  const handleConvert = async () => {
    if (accountMode === 'link' && !selectedAccountId) return;
    if (contactMode === 'link' && !selectedContactId) return;

    /* Conversion is a one-way door: the backend refuses a second attempt
       (`lead_already_converted`), so the user gets one chance to check what
       will be created versus linked before it happens. */
    const accountLabel =
      accountMode === 'link'
        ? (accountOptions.find((option) => option.value === selectedAccountId)?.label ??
          'the selected account')
        : `a new account "${suggestions?.suggested_account_name ?? lead.company ?? leadName}"`;
    const contactLabel =
      contactMode === 'link'
        ? (contactOptions.find((option) => option.value === selectedContactId)?.label ??
          'the selected contact')
        : `a new contact "${suggestions?.suggested_contact_name ?? leadName}"`;

    const confirmed = await confirm({
      title: `Convert ${leadName}?`,
      description: (
        <>
          <p>This cannot be undone. The lead moves to Converted and stays linked to what it produced.</p>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>
              Account: <strong>{accountMode === 'link' ? 'link ' : 'create '}</strong>
              {accountLabel}
            </li>
            <li>
              Contact: <strong>{contactMode === 'link' ? 'link ' : 'create '}</strong>
              {contactLabel}
            </li>
            <li>
              Opportunity:{' '}
              {createOpportunity
                ? `create "${dealName.trim() || suggestions?.suggested_opportunity_name || leadName}"`
                : 'none'}
            </li>
          </ul>
        </>
      ),
      confirmLabel: 'Convert lead',
      tone: 'warning',
    });
    if (!confirmed) return;

    const result = await run(() =>
      convertLead(lead.id, {
        account_id: accountMode === 'link' ? selectedAccountId : null,
        contact_id: contactMode === 'link' ? selectedContactId : null,
        create_opportunity: createOpportunity,
        opportunity_name: createOpportunity ? dealName.trim() || null : null,
        opportunity_value: createOpportunity ? dealValue || null : null,
        stage_id: createOpportunity ? stageId || null : null,
        expected_close_date: createOpportunity ? closeDate || null : null,
      }),
    );
    if (result === undefined) return;
    setConvertOpen(false);
    setConversionSuccess(result);
    notifySuccess(
      'Lead converted',
      result.opportunity_id
        ? 'Account, contact and opportunity are linked to this lead.'
        : 'Account and contact are linked to this lead.',
    );
    reload();
  };

  const sourceName =
    sources.find((source) => source.id === lead.lead_source_id)?.name ?? null;
  /* Resolving an owner to a name needs the member directory, which requires
     `users.VIEW` — a permission a rep does not hold. Falling back to the raw
     id printed a UUID at them and leaked another user's identifier for no
     benefit, so an unresolvable owner reads as "You" or as unknown instead. */
  const ownerName = (() => {
    if (!lead.owner_id) return null;
    const member = members.find((row) => row.user_id === lead.owner_id);
    if (member) return member.full_name?.trim() || member.email;
    if (lead.owner_id === signedInUserId) return 'You';
    return 'Another user';
  })();
  const convertedAtLabel = lead.converted_at
    ? new Date(lead.converted_at).toLocaleString()
    : null;

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
                onClick={openConvert}
                className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
                style={{ background: 'var(--accent)' }}
              >
                <GitBranch className="h-4 w-4" /> Convert Lead
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

      {conversionSuccess && (
        <div
          className="rounded-2xl border p-4"
          style={{ borderColor: 'var(--accent)', background: 'color-mix(in srgb, var(--accent) 8%, transparent)' }}
        >
          <p className="txt text-[13px] font-semibold">Lead converted successfully.</p>
          <p className="txt-muted mt-1 text-[12.5px]">
            Continue with the customer from Account, Contact
            {conversionSuccess.opportunity_id ? ', or Deal' : ''}.
          </p>
          <div className="mt-3 flex flex-wrap gap-3 text-[12.5px] font-semibold">
            <button
              type="button"
              onClick={() => router.push(`/accounts/${conversionSuccess.account_id}`)}
              style={{ color: 'var(--accent)' }}
            >
              Account →
            </button>
            <button
              type="button"
              onClick={() => router.push(`/contacts/${conversionSuccess.contact_id}`)}
              style={{ color: 'var(--accent)' }}
            >
              Contact →
            </button>
            {conversionSuccess.opportunity_id && (
              <button
                type="button"
                onClick={() =>
                  router.push(`/opportunities/${conversionSuccess.opportunity_id}`)
                }
                style={{ color: 'var(--accent)' }}
              >
                Deal →
              </button>
            )}
          </div>
        </div>
      )}

      {(converted || lead.converted_at) && (
        <div className="surface bd rounded-2xl border p-4">
          <p className="txt text-[13px] font-semibold">Conversion history</p>
          <p className="txt-muted mt-1 text-[12.5px]">
            Status: Converted
            {convertedAtLabel ? ` · ${convertedAtLabel}` : ''}
          </p>
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
                View deal →
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
            <Field label="Owner" value={ownerName} />
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

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Qualification" />
          <div className="space-y-4 pt-2">
            <Field label="Status" value={humanize(lead.status)} />
            <Field label="Lead source" value={sourceName} />
            <Field label="Product / service interest" value={lead.product_interest} />
            <Field
              label="Expected deal size"
              value={
                lead.expected_deal_size
                  ? Number(lead.expected_deal_size).toLocaleString(undefined, {
                      style: 'currency',
                      currency: 'USD',
                    })
                  : null
              }
            />
            {lead.lost_reason && <Field label="Reason" value={lead.lost_reason} />}
          </div>
        </div>
        {lead.notes ? (
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Notes" />
            <p className="txt whitespace-pre-wrap pt-1 text-[13.5px]">{lead.notes}</p>
          </div>
        ) : (
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Notes" />
            <p className="txt-muted pt-1 text-[13px]">No notes on this lead.</p>
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ActivityTimelinePanel entityType="LEAD" entityId={lead.id} />
        <NotesPanel entityType="LEAD" entityId={lead.id} />
        <AttachmentsPanel entityType="LEAD" entityId={lead.id} />
      </div>

      <SlideDrawer
        open={convertOpen}
        onClose={() => setConvertOpen(false)}
        title="Convert Lead"
        subtitle="Review account and contact, then optionally create a deal."
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
              disabled={
                pending ||
                convertLoading ||
                (accountMode === 'link' && !selectedAccountId) ||
                (contactMode === 'link' && !selectedContactId)
              }
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending ? 'Converting…' : 'Convert Lead'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          {convertLoading ? (
            <p className="txt-muted flex items-center gap-2 text-[12.5px]">
              <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
              Loading conversion options…
            </p>
          ) : (
            <p className="txt-muted text-[12.5px]">
              Convert{' '}
              <span className="txt font-semibold">
                {lead.first_name} {lead.last_name}
              </span>
              {suggestions?.suggested_account_name
                ? ` at ${suggestions.suggested_account_name}`
                : ''}
              . Account and contact are filled from this lead — only enter new deal details.
            </p>
          )}

          {!convertLoading &&
            suggestions &&
            suggestions.matching_accounts.length > 0 && (
              <div className="rounded-xl border border-amber-300/60 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
                <p className="font-semibold">Existing Account Found</p>
                <p className="mt-0.5 opacity-90">
                  {suggestions.matching_accounts.map((a) => a.name).join(', ')}. Link it
                  instead of creating a duplicate.
                </p>
              </div>
            )}
          {!convertLoading &&
            suggestions &&
            suggestions.matching_contacts.length > 0 && (
              <div className="rounded-xl border border-amber-300/60 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
                <p className="font-semibold">Existing Contact Found</p>
                <p className="mt-0.5 opacity-90">
                  {suggestions.matching_contacts
                    .map((c) => (c.email ? `${c.full_name} <${c.email}>` : c.full_name))
                    .join(', ')}
                  . Link them instead of creating a duplicate.
                </p>
              </div>
            )}

          <div className="space-y-2">
            <p className="txt text-[12px] font-semibold uppercase tracking-wide">Account</p>
            <label className="flex items-center gap-2 text-[13px] font-semibold">
              <input
                type="radio"
                name="account-mode"
                checked={accountMode === 'create'}
                onChange={() => {
                  setAccountMode('create');
                  setSelectedAccountId('');
                }}
              />
              Create new account
              {suggestions?.suggested_account_name ? (
                <span className="txt-muted font-normal">
                  ({suggestions.suggested_account_name})
                </span>
              ) : null}
            </label>
            <label className="flex items-center gap-2 text-[13px] font-semibold">
              <input
                type="radio"
                name="account-mode"
                checked={accountMode === 'link'}
                onChange={() => setAccountMode('link')}
                disabled={!mayViewAccounts || accountOptions.length === 0}
              />
              Link existing account
            </label>
            {accountMode === 'link' && (
              <FormField label="Account">
                <FormSelect
                  value={selectedAccountId}
                  onChange={(event) => {
                    setSelectedAccountId(event.target.value);
                    // Contact options change with the account; clear a stale pick.
                    setSelectedContactId('');
                  }}
                  placeholder="Select an account"
                  disabled={!mayViewAccounts}
                  options={accountOptions}
                />
              </FormField>
            )}
          </div>

          <div className="space-y-2">
            <p className="txt text-[12px] font-semibold uppercase tracking-wide">Contact</p>
            <label className="flex items-center gap-2 text-[13px] font-semibold">
              <input
                type="radio"
                name="contact-mode"
                checked={contactMode === 'create'}
                onChange={() => {
                  setContactMode('create');
                  setSelectedContactId('');
                }}
              />
              Create new contact
              {suggestions?.suggested_contact_name ? (
                <span className="txt-muted font-normal">
                  ({suggestions.suggested_contact_name})
                </span>
              ) : null}
            </label>
            <label className="flex items-center gap-2 text-[13px] font-semibold">
              <input
                type="radio"
                name="contact-mode"
                checked={contactMode === 'link'}
                onChange={() => setContactMode('link')}
                disabled={!mayViewContacts || contactOptions.length === 0}
              />
              Link existing contact
            </label>
            {contactMode === 'link' && (
              <FormField label="Contact">
                <FormSelect
                  value={selectedContactId}
                  onChange={(event) => setSelectedContactId(event.target.value)}
                  placeholder="Select a contact"
                  disabled={!mayViewContacts}
                  options={contactOptions}
                />
              </FormField>
            )}
          </div>

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
              <FormField
                label="Opening stage"
                hint="Left unset, the deal starts at the first stage of the pipeline."
              >
                <FormSelect
                  value={stageId}
                  onChange={(event) => setStageId(event.target.value)}
                  placeholder="First stage"
                  disabled={stages.length === 0}
                  options={stages.map((stage) => ({ value: stage.id, label: stage.name }))}
                />
              </FormField>
              <FormField label="Expected close date">
                <FormInput
                  type="date"
                  value={closeDate}
                  onChange={(event) => setCloseDate(event.target.value)}
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
