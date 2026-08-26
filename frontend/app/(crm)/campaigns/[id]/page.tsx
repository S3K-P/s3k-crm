'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Loader2, Megaphone, Plus, Trash2, UserPlus } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import AttachmentsPanel from '@/components/crm/shared/AttachmentsPanel';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import NotConfigured from '@/components/crm/shared/NotConfigured';
import { useRecord } from '@/components/crm/shared/useRecord';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormSelect } from '@/components/crm/forms/FormField';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import {
  addCampaignMember,
  getCampaign,
  listCampaignMembers,
  removeCampaignMember,
  type Campaign,
  type CampaignMember,
  type CampaignMemberType,
} from '@/features/crm/campaigns';
import { listLeads, type Lead } from '@/features/crm/leads';
import { listContacts, type Contact } from '@/features/crm/contacts';

/* ============================================================
   CAMPAIGN DETAIL

   Loads the campaign named by the route `[id]`. The previous
   version of this page read a module-level constant and ignored
   the URL entirely, so every campaign rendered the same
   fabricated record (risk R24) — that is what this replaces.

   Members are real rows from `crm.campaign_members`, added and
   removed through the API. The AI insights panel is gone: there
   is no AI backend, and a panel of invented "predicted ROI"
   numbers next to real ones is worse than no panel.
   ============================================================ */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="txt-muted text-[12px] font-semibold uppercase">{label}</p>
      <p className="txt mt-1 text-[13.5px]">{value || '—'}</p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="surface bd rounded-xl border p-4">
      <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wide">{label}</p>
      <p className="font-display txt mt-1 text-[22px] font-bold leading-none tabular-nums">
        {value}
      </p>
    </div>
  );
}

function formatMoney(value: string | null): string {
  if (value === null || value === '') return '—';
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return amount.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });
}

export default function CampaignDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;

  const { can } = usePermissions();
  const mayEdit = can('campaigns', 'EDIT');
  const mayViewLeads = can('leads', 'VIEW');
  const mayViewContacts = can('contacts', 'VIEW');

  const { status, data, error, reload } = useRecord<Campaign>(getCampaign, id, {
    errorMessage: 'Could not load this campaign.',
  });

  /* ---- Members ---- */
  const [members, setMembers] = useState<CampaignMember[] | null>(null);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [membersAttempt, setMembersAttempt] = useState(0);

  const reloadMembers = useCallback(() => setMembersAttempt((n) => n + 1), []);

  // Inline, so nothing is assigned to state before the first await.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await listCampaignMembers(id);
        if (!cancelled) {
          setMembers(loaded);
          setMembersError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setMembersError(describeApiError(caught, 'Could not load campaign members.'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, membersAttempt]);

  /* ---- Candidate pickers, so members show names rather than raw ids ---- */
  const [leads, setLeads] = useState<Lead[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (mayViewLeads) {
        try {
          const page = await listLeads({ page_size: 200, sort_by: 'created_at', sort_dir: 'desc' });
          if (!cancelled) setLeads(page.data);
        } catch {
          // The list still renders; member rows fall back to their id.
        }
      }
      if (mayViewContacts) {
        try {
          const page = await listContacts({ page_size: 200, sort_by: 'last_name', sort_dir: 'asc' });
          if (!cancelled) setContacts(page.data);
        } catch {
          /* as above */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewLeads, mayViewContacts]);

  const memberLabel = (member: CampaignMember): string => {
    if (member.entity_type === 'LEAD') {
      const lead = leads.find((candidate) => candidate.id === member.entity_id);
      return lead ? `${lead.first_name} ${lead.last_name}` : member.entity_id;
    }
    const contact = contacts.find((candidate) => candidate.id === member.entity_id);
    return contact ? contact.full_name : member.entity_id;
  };

  /* ---- Add-member drawer ---- */
  const [addOpen, setAddOpen] = useState(false);
  const [memberType, setMemberType] = useState<CampaignMemberType>('LEAD');
  const [entityId, setEntityId] = useState('');
  const { pending, error: mutationError, clearError, run } = useMutation();

  const handleAdd = async () => {
    if (!id || !entityId) return;
    const added = await run(() =>
      addCampaignMember(id, { entity_type: memberType, entity_id: entityId }),
    );
    if (added === undefined) return;
    setAddOpen(false);
    setEntityId('');
    reloadMembers();
    reload(); // member_count is computed server-side
  };

  const handleRemove = async (member: CampaignMember) => {
    if (!id) return;
    const done = await run(() => removeCampaignMember(id, member.id));
    if (done === undefined) return;
    reloadMembers();
    reload();
  };

  if (status === 'loading') {
    return (
      <div className="txt-muted flex items-center gap-2 p-8 text-[13px]">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading campaign…
      </div>
    );
  }

  if (status === 'missing') {
    return (
      <div className="space-y-4 p-6 lg:p-8">
        <button
          type="button"
          onClick={() => router.push('/campaigns')}
          className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
        >
          <ArrowLeft className="h-4 w-4" /> Back to campaigns
        </button>
        <div className="surface bd rounded-2xl border p-10 text-center">
          <p className="txt text-[14px] font-semibold">Campaign not found</p>
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
        <ListError message={error ?? 'Could not load this campaign.'} onRetry={reload} />
      </div>
    );
  }

  const campaign = data;
  const candidates = memberType === 'LEAD' ? leads : contacts;
  const enrolled = new Set((members ?? []).map((member) => member.entity_id));

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <button
        type="button"
        onClick={() => router.push('/campaigns')}
        className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to campaigns
      </button>

      <div className="flex flex-wrap items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-fuchsia-500 to-purple-600">
          <Megaphone className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">{campaign.name}</h1>
          <p className="txt-muted mt-0.5 text-[13px]">{humanize(campaign.type)}</p>
        </div>
        <div className="ml-auto">
          <StatusBadge
            label={humanize(campaign.status)}
            variant={statusVariant(campaign.status)}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Leads generated" value={String(campaign.leads_generated)} />
        <Metric label="Opportunities" value={String(campaign.opportunities_generated)} />
        <Metric label="Members" value={String(campaign.member_count)} />
        <Metric label="Budget" value={formatMoney(campaign.budget)} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Schedule and targeting" />
          <div className="space-y-4 pt-2">
            <Field label="Starts" value={campaign.start_date} />
            <Field label="Ends" value={campaign.end_date} />
            <Field label="Target audience" value={campaign.target_audience} />
            <Field label="Products" value={campaign.products} />
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Financials" />
          <div className="space-y-4 pt-2">
            <Field label="Budget" value={formatMoney(campaign.budget)} />
            <Field label="Expected revenue" value={formatMoney(campaign.expected_revenue)} />
            <Field
              label="Conversion rate"
              value={campaign.conversion_rate ? `${Number(campaign.conversion_rate).toFixed(1)}%` : null}
            />
            <Field label="ROI" value={campaign.roi ? `${Number(campaign.roi).toFixed(1)}%` : null} />
          </div>
          <p className="txt-faint mt-4 text-[11.5px] leading-relaxed">
            Conversion rate and ROI are computed by the backend. The scheduled recomputation job is
            not built yet, so a new campaign reports no value rather than an estimated one.
          </p>
        </div>
      </div>

      {campaign.notes && (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Notes" />
          <p className="txt whitespace-pre-wrap pt-1 text-[13.5px]">{campaign.notes}</p>
        </div>
      )}

      {/* ---- Members ---- */}
      <div className="surface bd rounded-2xl border p-5">
        <div className="flex items-center justify-between gap-3">
          <SectionHeader title="Campaign members" />
          {mayEdit && (
            <button
              type="button"
              onClick={() => {
                clearError();
                setAddOpen(true);
              }}
              className="ctl bd flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80"
            >
              <UserPlus className="h-3.5 w-3.5" /> Add member
            </button>
          )}
        </div>

        <div className="pt-3">
          {membersError !== null ? (
            <p role="alert" className="text-[12.5px] font-medium text-red-500">
              {membersError}
            </p>
          ) : members === null ? (
            <p className="txt-faint flex items-center gap-2 py-6 text-[12.5px]">
              <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" /> Loading members…
            </p>
          ) : members.length === 0 ? (
            <p className="txt-faint py-6 text-center text-[12.5px]">
              No leads or contacts are enrolled in this campaign yet.
            </p>
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {members.map((member) => (
                <li key={member.id} className="flex items-center gap-3 py-2.5">
                  <StatusBadge label={humanize(member.entity_type)} variant="neutral" />
                  <button
                    type="button"
                    onClick={() =>
                      router.push(
                        member.entity_type === 'LEAD'
                          ? `/leads/${member.entity_id}`
                          : `/contacts/${member.entity_id}`,
                      )
                    }
                    className="txt min-w-0 flex-1 truncate text-left text-[13px] font-medium hover:underline"
                  >
                    {memberLabel(member)}
                  </button>
                  {mayEdit && (
                    <button
                      type="button"
                      aria-label="Remove from campaign"
                      onClick={() => void handleRemove(member)}
                      className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ActivityTimelinePanel entityType="CAMPAIGN" entityId={campaign.id} />
        <NotesPanel entityType="CAMPAIGN" entityId={campaign.id} />
        <AttachmentsPanel entityType="CAMPAIGN" entityId={campaign.id} />
      </div>

      <NotConfigured
        compact
        title="Campaign AI insights are not available"
        description="Predicted performance, audience recommendations and channel analysis need the AI gateway, which has not been built. This panel previously showed a fixed sample forecast; it now shows nothing rather than a number you could mistake for a prediction about this campaign."
        requires="AI gateway (ADR-016, Phase 5)"
      />

      <SlideDrawer
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add campaign member"
        subtitle="Enrol an existing lead or contact."
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleAdd()}
              disabled={pending || !entityId}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending ? (
                <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              {pending ? 'Adding…' : 'Add'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <FormField label="Record type">
            <FormSelect
              value={memberType}
              onChange={(event) => {
                setMemberType(event.target.value as CampaignMemberType);
                setEntityId('');
              }}
              options={[
                { value: 'LEAD', label: 'Lead' },
                { value: 'CONTACT', label: 'Contact' },
              ]}
            />
          </FormField>

          <FormField
            label={memberType === 'LEAD' ? 'Lead' : 'Contact'}
            required
            hint="Records already enrolled are not listed."
          >
            <FormSelect
              value={entityId}
              onChange={(event) => setEntityId(event.target.value)}
              placeholder={`Choose a ${memberType === 'LEAD' ? 'lead' : 'contact'}…`}
              options={candidates
                .filter((candidate) => !enrolled.has(candidate.id))
                .map((candidate) => ({
                  value: candidate.id,
                  label:
                    'full_name' in candidate
                      ? candidate.full_name
                      : `${candidate.first_name} ${candidate.last_name}`,
                }))}
            />
          </FormField>

          <FormError message={mutationError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
