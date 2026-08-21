'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Target, Loader2, RotateCcw } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { ListError } from '@/components/crm/shared/ListStates';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import { useRecord } from '@/components/crm/shared/useRecord';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { getAccount } from '@/features/crm/accounts';
import { getContact } from '@/features/crm/contacts';
import {
  changeStage,
  getOpportunity,
  isClosed,
  listStages,
  reopenOpportunity,
  stageHistory,
  type Opportunity,
  type PipelineStage,
  type StageHistoryEntry,
} from '@/features/crm/opportunities';

/* ============================================================
   OPPORTUNITY DETAIL

   Loads the deal named by the route `[id]`, along with its real
   stage history from `GET /crm/opportunities/{id}/history` —
   every stage move the backend recorded, with who made it and
   when.
   ============================================================ */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="txt-muted text-[12px] font-semibold uppercase">{label}</p>
      <p className="txt mt-1 text-[13.5px]">{value || '—'}</p>
    </div>
  );
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function OpportunityDetailPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;
  const { can } = usePermissions();
  const mayEdit = can('opportunities', 'EDIT');

  const { status, data, error, reload } = useRecord<Opportunity>(getOpportunity, id, {
    errorMessage: 'Could not load this opportunity.',
  });

  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [history, setHistory] = useState<StageHistoryEntry[]>([]);
  const [stageError, setStageError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await listStages();
        if (!cancelled) setStages(result);
      } catch {
        // The page still renders; only the stage control is unavailable.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!id || status !== 'ready') return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await stageHistory(id);
        if (!cancelled) setHistory(result);
      } catch {
        // History is supplementary; its absence must not blank the page.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, status]);

  /* ---- Names for the related records, so the links read as records ----
     Each is fetched by id; a failure leaves the link in place with generic
     text rather than removing the only route to the account. */
  const accountId = data?.account_id ?? null;
  const contactId = data?.primary_contact_id ?? null;
  const [accountName, setAccountName] = useState<string | null>(null);
  const [contactName, setContactName] = useState<string | null>(null);

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

  useEffect(() => {
    if (!contactId) return;
    let cancelled = false;
    void (async () => {
      try {
        const contact = await getContact(contactId);
        if (!cancelled) setContactName(contact.full_name);
      } catch {
        if (!cancelled) setContactName(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [contactId]);

  if (status === 'loading') {
    return (
      <div className="txt-muted flex items-center gap-2 p-8 text-[13px]">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading opportunity…
      </div>
    );
  }

  if (status === 'missing') {
    return (
      <div className="space-y-4 p-6 lg:p-8">
        <button
          type="button"
          onClick={() => router.push('/opportunities')}
          className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
        >
          <ArrowLeft className="h-4 w-4" /> Back to opportunities
        </button>
        <div className="surface bd rounded-2xl border p-10 text-center">
          <p className="txt text-[14px] font-semibold">Opportunity not found</p>
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
        <ListError message={error ?? 'Could not load this opportunity.'} onRetry={reload} />
      </div>
    );
  }

  const opportunity = data;
  const closed = isClosed(opportunity);
  const stageName = stages.find((s) => s.id === opportunity.stage_id)?.name ?? 'Unknown';

  const handleStage = async (stageId: string) => {
    setStageError(null);
    const target = stages.find((s) => s.id === stageId);
    if (target === undefined || target.id === opportunity.stage_id) return;

    /* Closing is confirmed in both directions: it stamps won_at/lost_at and
       locks the record until an explicit reopen. The loss reason the backend
       insists on is collected in the same dialog. */
    let lossReason: string | null = null;
    if (target.is_lost) {
      const answer = await confirm({
        title: `Mark "${opportunity.name}" as lost?`,
        description:
          'The deal closes and leaves the open pipeline. It becomes read-only until it is reopened.',
        confirmLabel: 'Mark as lost',
        tone: 'danger',
        prompt: {
          label: 'Why was this deal lost?',
          required: true,
          placeholder: 'Lost on price, chose a competitor, project cancelled…',
          hint: 'Stored on the deal and used for loss analysis.',
        },
      });
      if (!answer) return;
      lossReason = answer.value;
    } else if (target.is_won) {
      const answer = await confirm({
        title: `Mark "${opportunity.name}" as won?`,
        description:
          'The deal closes at 100% and counts towards won revenue. It becomes read-only until it is reopened.',
        confirmLabel: 'Mark as won',
        tone: 'warning',
      });
      if (!answer) return;
    }

    try {
      await changeStage(opportunity.id, { stage_id: stageId, loss_reason: lossReason });
      notifySuccess(
        target.is_won
          ? 'Deal marked as won'
          : target.is_lost
            ? 'Deal marked as lost'
            : 'Stage updated',
        `${opportunity.name} → ${target.name}`,
      );
      reload();
      if (id) setHistory(await stageHistory(id));
    } catch (caught) {
      setStageError(describeApiError(caught, 'That stage change was rejected.'));
      notifyError(caught, 'That stage change was rejected.');
    }
  };

  /* Reopening a closed deal. The endpoint has existed since the stage
     workflow landed but had no control anywhere in the UI, which left a
     mis-clicked "Closed Won" permanently stuck. */
  const handleReopen = async () => {
    const openStages = stages.filter((stage) => !stage.is_won && !stage.is_lost);
    const target = openStages[0];
    if (target === undefined) {
      notifyError(null, 'No open stage is configured to reopen this deal into.');
      return;
    }
    const ok = await confirm({
      title: `Reopen "${opportunity.name}"?`,
      description: `The deal returns to ${target.name}. Its won/lost outcome and reason are cleared, and it starts counting towards open pipeline again.`,
      confirmLabel: 'Reopen deal',
      tone: 'warning',
    });
    if (!ok) return;
    try {
      await reopenOpportunity(opportunity.id, target.id);
      notifySuccess('Opportunity reopened', `${opportunity.name} → ${target.name}`);
      reload();
      if (id) setHistory(await stageHistory(id));
    } catch (caught) {
      notifyError(caught, 'The opportunity could not be reopened.');
    }
  };

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <button
        type="button"
        onClick={() => router.push('/opportunities')}
        className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to opportunities
      </button>

      <div className="flex flex-wrap items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
          <Target className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">{opportunity.name}</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            {opportunity.deal_value
              ? `${opportunity.currency} ${Number(opportunity.deal_value).toLocaleString()}`
              : 'No deal value recorded'}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StatusBadge
            label={stageName}
            variant={
              opportunity.won_at ? 'success' : opportunity.lost_at ? 'danger' : 'accent'
            }
          />
          {mayEdit && !closed && stages.length > 0 && (
            <FilterSelect
              value={opportunity.stage_id}
              onChange={(event) => void handleStage(event.target.value)}
              aria-label="Change stage"
              options={stages.map((stage) => ({ value: stage.id, label: stage.name }))}
            />
          )}
        </div>
      </div>

      {stageError && (
        <p role="alert" className="text-[12.5px] font-medium text-red-500">
          {stageError}
        </p>
      )}

      {closed && (
        <div className="surface bd flex flex-wrap items-center gap-3 rounded-2xl border p-4">
          <div className="min-w-0 flex-1">
            <p className="txt text-[13px] font-semibold">
              {opportunity.won_at ? 'This deal was won.' : 'This deal was lost.'}
            </p>
            {opportunity.loss_reason && (
              <p className="txt-muted mt-1 text-[12.5px]">Reason: {opportunity.loss_reason}</p>
            )}
            {opportunity.win_reason && (
              <p className="txt-muted mt-1 text-[12.5px]">Reason: {opportunity.win_reason}</p>
            )}
            <p className="txt-faint mt-1 text-[12px]">
              A closed deal is read-only. Reopen it to change the stage or its details.
            </p>
          </div>
          {mayEdit && (
            <button
              type="button"
              onClick={() => void handleReopen()}
              className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Reopen deal
            </button>
          )}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Deal" />
          <div className="space-y-4 pt-2">
            <div>
              <p className="txt-muted text-[12px] font-semibold uppercase">Account</p>
              {/* The deal's owning account. It was previously rendered as a
                  raw UUID, which made the opportunity a dead end. */}
              <button
                type="button"
                onClick={() => router.push(`/accounts/${opportunity.account_id}`)}
                className="mt-1 text-left text-[13.5px] font-semibold hover:underline"
                style={{ color: 'var(--accent)' }}
              >
                {accountName ?? 'Open account'}
              </button>
            </div>
            {opportunity.primary_contact_id && (
              <div>
                <p className="txt-muted text-[12px] font-semibold uppercase">Primary contact</p>
                <button
                  type="button"
                  onClick={() => router.push(`/contacts/${opportunity.primary_contact_id}`)}
                  className="mt-1 text-left text-[13.5px] font-semibold hover:underline"
                  style={{ color: 'var(--accent)' }}
                >
                  {contactName ?? 'Open contact'}
                </button>
              </div>
            )}
            <Field label="Currency" value={opportunity.currency} />
            <Field
              label="Win probability"
              value={
                opportunity.win_probability !== null
                  ? `${opportunity.win_probability}%`
                  : null
              }
            />
            <Field label="Expected close" value={opportunity.expected_close_date} />
            <Field label="Forecast category" value={opportunity.forecast_category} />
            <Field label="Competitor" value={opportunity.competitor} />
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Stage history" />
          {history.length === 0 ? (
            <p className="txt-faint py-4 text-center text-[12.5px]">
              No stage changes recorded yet.
            </p>
          ) : (
            <ul className="space-y-3 pt-1">
              {history.map((entry) => (
                <li key={entry.id} className="flex items-start gap-3">
                  <span
                    className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: 'var(--accent)' }}
                    aria-hidden="true"
                  />
                  <div>
                    <p className="txt text-[13px] font-semibold">
                      {stages.find((s) => s.id === entry.to_stage_id)?.name ?? 'Stage change'}
                    </p>
                    <p className="txt-faint text-[11.5px]">{formatWhen(entry.changed_at)}</p>
                    {entry.note && (
                      <p className="txt-muted mt-0.5 text-[12.5px]">{entry.note}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ActivityTimelinePanel entityType="OPPORTUNITY" entityId={opportunity.id} />
        <NotesPanel entityType="OPPORTUNITY" entityId={opportunity.id} />
      </div>
    </div>
  );
}
