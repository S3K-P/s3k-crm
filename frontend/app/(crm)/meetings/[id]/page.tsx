'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, CalendarDays, Check, Loader2, Video, X } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import { NotesPanel } from '@/components/crm/shared/RecordPanels';
import NotConfigured from '@/components/crm/shared/NotConfigured';
import { useRecord } from '@/components/crm/shared/useRecord';
import { useRelatedRecordOptions } from '@/components/crm/forms/RelatedRecordFields';
import { usePermissions } from '@/context/AuthContext';
import { useMutation } from '@/features/shared/hooks/useCollection';
import {
  getMeeting,
  meetingDetail,
  updateMeeting,
  type Meeting,
} from '@/features/crm/meetings';
import type { ActivityStatus } from '@/features/crm/activities';

/* ============================================================
   MEETING DETAIL

   Resolves the activity named by the route `[id]`. The previous
   version rendered a module-level `MOCK_MEETING` and never read
   the URL, so every meeting id showed the same invented record.

   Marking a meeting completed or cancelled writes through
   `PATCH /crm/activities/{id}`; the backend derives
   `completed_at` from the status, so it is never sent.
   ============================================================ */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="txt-muted text-[12px] font-semibold uppercase">{label}</p>
      <p className="txt mt-1 text-[13.5px]">{value || '—'}</p>
    </div>
  );
}

function formatWhen(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function MeetingDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === 'string' ? params.id : undefined;

  const { can } = usePermissions();
  const mayEdit = can('activities', 'EDIT');

  const { status, data, error, reload } = useRecord<Meeting>(getMeeting, id, {
    errorMessage: 'Could not load this meeting.',
  });

  const related = useRelatedRecordOptions();
  const { pending, error: saveError, run } = useMutation();
  const [actioned, setActioned] = useState<ActivityStatus | null>(null);

  const setStatus = async (next: ActivityStatus) => {
    if (!id) return;
    setActioned(next);
    const saved = await run(() => updateMeeting(id, { status: next }));
    setActioned(null);
    if (saved !== undefined) reload();
  };

  if (status === 'loading') {
    return (
      <div className="txt-muted flex items-center gap-2 p-8 text-[13px]">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading meeting…
      </div>
    );
  }

  if (status === 'missing') {
    return (
      <div className="space-y-4 p-6 lg:p-8">
        <button
          type="button"
          onClick={() => router.push('/meetings')}
          className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
        >
          <ArrowLeft className="h-4 w-4" /> Back to meetings
        </button>
        <div className="surface bd rounded-2xl border p-10 text-center">
          <p className="txt text-[14px] font-semibold">Meeting not found</p>
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
        <ListError message={error ?? 'Could not load this meeting.'} onRetry={reload} />
      </div>
    );
  }

  const meeting = data;
  const detail = meetingDetail(meeting);
  const open = meeting.status === 'PLANNED';

  return (
    <div className="space-y-6 p-6 lg:p-8">
      <button
        type="button"
        onClick={() => router.push('/meetings')}
        className="txt-muted flex items-center gap-1.5 text-[13px] font-semibold hover:opacity-70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to meetings
      </button>

      <div className="flex flex-wrap items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
          <CalendarDays className="h-5 w-5 text-white" />
        </div>
        <div className="min-w-0">
          <h1 className="font-display txt text-[22px] font-extrabold">{meeting.subject}</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            {formatWhen(detail?.start_time) ?? 'No start time recorded'}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StatusBadge label={humanize(meeting.status)} variant={statusVariant(meeting.status)} />
          {mayEdit && open && (
            <>
              <button
                type="button"
                onClick={() => void setStatus('COMPLETED')}
                disabled={pending}
                className="ctl bd flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:opacity-50"
              >
                {pending && actioned === 'COMPLETED' ? (
                  <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                Mark held
              </button>
              <button
                type="button"
                onClick={() => void setStatus('CANCELLED')}
                disabled={pending}
                className="ctl bd flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold text-red-500 transition hover:opacity-80 disabled:opacity-50"
              >
                {pending && actioned === 'CANCELLED' ? (
                  <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
                ) : (
                  <X className="h-3.5 w-3.5" />
                )}
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      <FormError message={saveError} />

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Schedule" />
          <div className="space-y-4 pt-2">
            <Field label="Starts" value={formatWhen(detail?.start_time)} />
            <Field label="Ends" value={formatWhen(detail?.end_time)} />
            <Field label="Format" value={detail ? humanize(detail.meeting_type) : null} />
            <Field label="Location" value={detail?.location ?? null} />
          </div>
          {detail?.meeting_link && (
            <a
              href={detail.meeting_link}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              <Video className="h-3.5 w-3.5" /> Join meeting
            </a>
          )}
        </div>

        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Context" />
          <div className="space-y-4 pt-2">
            <div>
              <p className="txt-muted text-[12px] font-semibold uppercase">Linked record</p>
              {meeting.related_entity_type && meeting.related_entity_id ? (
                <button
                  type="button"
                  onClick={() => {
                    const routes: Record<string, string> = {
                      ACCOUNT: 'accounts',
                      CONTACT: 'contacts',
                      LEAD: 'leads',
                      OPPORTUNITY: 'opportunities',
                      CAMPAIGN: 'campaigns',
                    };
                    const segment = routes[meeting.related_entity_type as string];
                    if (segment) router.push(`/${segment}/${meeting.related_entity_id}`);
                  }}
                  className="mt-1 text-left text-[13.5px] font-semibold hover:underline"
                  style={{ color: 'var(--accent)' }}
                >
                  {related.label(meeting.related_entity_type, meeting.related_entity_id)}
                </button>
              ) : (
                <p className="txt mt-1 text-[13.5px]">Not linked to a record</p>
              )}
            </div>
            <Field label="Agenda" value={detail?.agenda ?? null} />
            <Field label="Outcome" value={meeting.outcome} />
          </div>
        </div>
      </div>

      {meeting.description && (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Notes" />
          <p className="txt whitespace-pre-wrap pt-1 text-[13.5px]">{meeting.description}</p>
        </div>
      )}

      {meeting.related_entity_type && meeting.related_entity_id && (
        <NotesPanel
          entityType={meeting.related_entity_type}
          entityId={meeting.related_entity_id}
        />
      )}

      <NotConfigured
        compact
        title="Meeting AI assistant is not available"
        description="Automatic transcription, summaries and follow-up suggestions need the AI gateway, which has not been built. This panel previously showed a fixed sample summary that was never derived from this meeting."
        requires="AI gateway (ADR-016, Phase 5)"
      />
    </div>
  );
}
