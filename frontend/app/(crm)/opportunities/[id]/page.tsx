'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Target, Loader2 } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { ListError } from '@/components/crm/shared/ListStates';
import { ActivityTimelinePanel, NotesPanel } from '@/components/crm/shared/RecordPanels';
import { useRecord } from '@/components/crm/shared/useRecord';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  changeStage,
  getOpportunity,
  isClosed,
  listStages,
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
            It may have been archived, or it belongs to another organization.
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
    let lossReason: string | null = null;
    if (target?.is_lost) {
      lossReason = window.prompt('Why was this deal lost?')?.trim() || null;
      if (!lossReason) return;
    }
    try {
      await changeStage(opportunity.id, { stage_id: stageId, loss_reason: lossReason });
      reload();
      if (id) setHistory(await stageHistory(id));
    } catch (caught) {
      setStageError(describeApiError(caught, 'That stage change was rejected.'));
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
        <div className="surface bd rounded-2xl border p-4">
          <p className="txt text-[13px] font-semibold">
            {opportunity.won_at ? 'This deal was won.' : 'This deal was lost.'}
          </p>
          {opportunity.loss_reason && (
            <p className="txt-muted mt-1 text-[12.5px]">Reason: {opportunity.loss_reason}</p>
          )}
          {opportunity.win_reason && (
            <p className="txt-muted mt-1 text-[12.5px]">Reason: {opportunity.win_reason}</p>
          )}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Deal" />
          <div className="space-y-4 pt-2">
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
