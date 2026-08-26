'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, CheckCircle2, GitBranch, ListChecks, Loader2, XCircle } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import NotConfigured, { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { useRecord } from '@/components/crm/shared/useRecord';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormTextarea } from '@/components/crm/forms/FormField';
import { notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { useMutation } from '@/features/shared/hooks/useCollection';
import { getLead } from '@/features/crm/leads';
import { getLeadSource, type LeadSource } from '@/features/crm/lead-sources';
import {
  SCORECARD_UNAVAILABLE,
  STAGE_LABELS,
  disqualify,
  markQualified,
  qualificationStage,
  type Lead,
} from '@/features/crm/qualification';

/* ============================================================
   QUALIFICATION REVIEW

   Resolves the lead named by the route `[id]` — the previous
   version rendered a constant and ignored the URL entirely.

   Both actions here are real lead transitions the backend
   validates: "Qualify" moves CONTACTED -> QUALIFIED, and
   "Disqualify" moves any open status -> LOST with a reason. An
   illegal transition comes back as 422 and is shown, not
   swallowed.

   The BANT scorecard is absent for the reason given in
   `SCORECARD_UNAVAILABLE`: there is no table to store it in.
   ============================================================ */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="txt-muted text-[12px] font-semibold uppercase">{label}</p>
      <p className="txt mt-1 text-[13.5px]">{value || '—'}</p>
    </div>
  );
}

export default function QualificationDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;

  const { can } = usePermissions();
  const mayEdit = can('leads', 'EDIT');
  const mayViewSources = can('lead_sources', 'VIEW');

  const { status, data, error, reload } = useRecord<Lead>(getLead, id, {
    errorMessage: 'Could not load this lead.',
  });

  /* The source is stored with the id it was fetched for, so a stale name from
     a previously viewed lead can never be shown against this one — which is
     also why nothing needs to be cleared synchronously when the id changes. */
  const [source, setSource] = useState<{ id: string; record: LeadSource } | null>(null);
  const sourceId = data?.lead_source_id ?? null;

  useEffect(() => {
    if (!sourceId || !mayViewSources) return;
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await getLeadSource(sourceId);
        if (!cancelled) setSource({ id: sourceId, record: loaded });
      } catch {
        // The field falls back to "Source not readable" below.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sourceId, mayViewSources]);

  const sourceName = source !== null && source.id === sourceId ? source.record.name : null;

  const { pending, error: actionError, clearError, run } = useMutation();
  const [disqualifyOpen, setDisqualifyOpen] = useState(false);
  const [reason, setReason] = useState('');

  const handleQualify = async () => {
    if (!id) return;
    const saved = await run(() => markQualified(id));
    if (saved === undefined) return;
    notifySuccess('Lead qualified', 'It can now be converted from the lead record.');
    reload();
  };

  const handleDisqualify = async () => {
    if (!id || !reason.trim()) return;
    const saved = await run(() => disqualify(id, reason.trim()));
    if (saved === undefined) return;
    setDisqualifyOpen(false);
    setReason('');
    notifySuccess('Lead disqualified', 'It has left the active pipeline.');
    reload();
  };

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
          onClick={() => router.push('/qualification')}
          className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
        >
          <ArrowLeft className="h-4 w-4" /> Back to qualification
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
  const stage = qualificationStage(lead);
  const open = stage !== 'CLOSED';

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <button
        type="button"
        onClick={() => router.push('/qualification')}
        className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to qualification
      </button>

      <div className="flex flex-wrap items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-emerald-500 to-green-600">
          <ListChecks className="h-5 w-5 text-white" />
        </div>
        <div className="min-w-0">
          <h1 className="font-display txt text-[22px] font-extrabold">
            {lead.first_name} {lead.last_name}
          </h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            {lead.company ?? 'No company recorded'} · {STAGE_LABELS[stage]}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <StatusBadge label={humanize(lead.status)} variant={statusVariant(lead.status)} />
          {mayEdit && lead.status === 'CONTACTED' && (
            <button
              type="button"
              onClick={() => void handleQualify()}
              disabled={pending}
              className="ctl bd flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:opacity-50"
            >
              {pending ? (
                <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" />
              )}
              Qualify
            </button>
          )}
          {mayEdit && open && (
            <button
              type="button"
              onClick={() => {
                clearError();
                setDisqualifyOpen(true);
              }}
              className="ctl bd flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold text-red-500 transition hover:opacity-80"
            >
              <XCircle className="h-3.5 w-3.5" /> Disqualify
            </button>
          )}
          {mayEdit && lead.status === 'QUALIFIED' && (
            <button
              type="button"
              onClick={() => router.push(`/leads/${lead.id}`)}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              <GitBranch className="h-3.5 w-3.5" /> Convert
            </button>
          )}
        </div>
      </div>

      <FormError message={actionError} />

      <PartialDataNotice>{SCORECARD_UNAVAILABLE}</PartialDataNotice>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Lead" />
          <div className="space-y-4 pt-2">
            <Field label="Email" value={lead.email} />
            <Field label="Phone" value={lead.phone} />
            <Field label="Company" value={lead.company} />
            <Field label="Industry" value={lead.industry} />
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Qualification context" />
          <div className="space-y-4 pt-2">
            <Field
              label="Source"
              value={sourceName ?? (lead.lead_source_id ? "Source not readable" : null)}
            />
            <Field label="Priority" value={lead.priority ? humanize(lead.priority) : null} />
            <Field label="Company size" value={lead.company_size} />
            <Field
              label="Expected deal size"
              value={
                lead.expected_deal_size
                  ? Number(lead.expected_deal_size).toLocaleString(undefined, {
                      style: 'currency',
                      currency: 'USD',
                      maximumFractionDigits: 0,
                    })
                  : null
              }
            />
            {lead.lost_reason && <Field label="Disqualified because" value={lead.lost_reason} />}
          </div>
        </div>
      </div>

      {lead.notes && (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Lead notes" />
          <p className="txt whitespace-pre-wrap pt-1 text-[13.5px]">{lead.notes}</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <ActivityTimelinePanel entityType="LEAD" entityId={lead.id} />
        <NotesPanel entityType="LEAD" entityId={lead.id} />
      </div>

      <NotConfigured
        compact
        title="AI qualification assistant is not available"
        description="Automatic scoring, fit analysis and recommended next steps need the AI gateway, which has not been built. This panel previously showed fixed sample values that were never computed from this lead."
        requires="AI gateway (ADR-016, Phase 5)"
      />

      <SlideDrawer
        open={disqualifyOpen}
        onClose={() => setDisqualifyOpen(false)}
        title="Disqualify lead"
        subtitle="The lead moves to Lost. It can be reopened later."
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setDisqualifyOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleDisqualify()}
              disabled={pending || !reason.trim()}
              className="flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending ? 'Saving…' : 'Disqualify'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <FormField label="Reason" required hint="Stored on the lead as its lost reason.">
            <FormTextarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              placeholder="No budget this year, no decision maker identified…"
            />
          </FormField>
          <FormError message={actionError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
