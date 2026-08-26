'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CalendarDays, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess, notifyWarning } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import RelatedRecordFields, {
  useRelatedRecordOptions,
} from '@/components/crm/forms/RelatedRecordFields';
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import {
  MEETING_STATUSES,
  MEETING_TYPES,
  archiveMeeting,
  createMeeting,
  listMeetings,
  meetingDetail,
  updateMeeting,
  type Meeting,
  type MeetingInput,
  type MeetingType,
} from '@/features/crm/meetings';
import type { ActivityStatus } from '@/features/crm/activities';
import type { CrmEntityType } from '@/features/crm/tasks';

/* ============================================================
   MEETINGS

   A meeting is an activity of type MEETING carrying a one-to-one
   scheduling extension, so every row here comes from
   `GET /api/v1/crm/activities?type=MEETING`. There is no separate
   meetings table and no separate endpoint — which is what keeps a
   meeting visible on the timeline of the account, contact, lead
   or opportunity it was booked against.

   `datetime-local` inputs are wall-clock strings with no zone.
   They are converted to a real instant before being sent, because
   the backend column is timezone-aware and a naive string would
   be silently reinterpreted.
   ============================================================ */

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...MEETING_STATUSES.map((value) => ({ value, label: humanize(value) })),
];

interface MeetingForm {
  subject: string;
  description: string;
  status: ActivityStatus;
  meeting_type: MeetingType;
  start_time: string;
  end_time: string;
  location: string;
  meeting_link: string;
  agenda: string;
  related_entity_type: CrmEntityType | '';
  related_entity_id: string;
}

const EMPTY_FORM: MeetingForm = {
  subject: '',
  description: '',
  status: 'PLANNED',
  meeting_type: 'VIDEO',
  start_time: '',
  end_time: '',
  location: '',
  meeting_link: '',
  agenda: '',
  related_entity_type: '',
  related_entity_id: '',
};

/** `2026-08-18T14:30` (local wall clock) -> ISO instant. */
function toInstant(local: string): string | null {
  if (!local) return null;
  const parsed = new Date(local);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

/** ISO instant -> the `datetime-local` value for the reader's own zone. */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function MeetingsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('activities', 'CREATE');
  const mayEdit = can('activities', 'EDIT');
  const mayDelete = can('activities', 'DELETE');

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () =>
      listMeetings({
        page,
        page_size: 25,
        search: search.trim() || null,
        status: (statusFilter || null) as ActivityStatus | null,
        sort_by: 'created_at',
        sort_dir: 'desc',
      }),
    [page, search, statusFilter],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Meeting>(
    fetcher,
    [page, search, statusFilter],
    { errorMessage: 'Something went wrong loading meetings.' },
  );

  const related = useRelatedRecordOptions();

  /* ---- Drawer ---- */
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Meeting | null>(null);
  const [form, setForm] = useState<MeetingForm>(EMPTY_FORM);
  const { pending, error: saveError, clearError, run } = useMutation();
  /** Client-side form complaints, kept apart from the API's own errors. */
  const [validation, setValidation] = useState<string | null>(null);

  const openAdd = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    clearError();
    setValidation(null);
    setDrawerOpen(true);
  };

  const openEdit = (row: Meeting) => {
    const detail = meetingDetail(row);
    setEditing(row);
    setForm({
      subject: row.subject,
      description: row.description ?? '',
      status: row.status,
      meeting_type: detail?.meeting_type ?? 'VIDEO',
      start_time: toLocalInput(detail?.start_time),
      end_time: toLocalInput(detail?.end_time),
      location: detail?.location ?? '',
      meeting_link: detail?.meeting_link ?? '',
      agenda: detail?.agenda ?? '',
      related_entity_type: row.related_entity_type ?? '',
      related_entity_id: row.related_entity_id ?? '',
    });
    clearError();
    setValidation(null);
    setDrawerOpen(true);
  };


  const handleSave = async () => {
    const startsAt = toInstant(form.start_time);
    if (!form.subject.trim() || startsAt === null) {
      setValidation('A title and a start time are required.');
      return;
    }
    const endsAt = toInstant(form.end_time);
    if (endsAt !== null && endsAt <= startsAt) {
      setValidation('The end time must come after the start time.');
      return;
    }
    setValidation(null);

    const body: MeetingInput = {
      subject: form.subject.trim(),
      description: form.description.trim() || null,
      status: form.status,
      related_entity_type: form.related_entity_type || null,
      related_entity_id: form.related_entity_id || null,
      meeting: {
        meeting_type: form.meeting_type,
        start_time: startsAt,
        end_time: endsAt,
        location: form.location.trim() || null,
        meeting_link: form.meeting_link.trim() || null,
        agenda: form.agenda.trim() || null,
      },
    };

    const saved = await run(() =>
      editing ? updateMeeting(editing.id, body) : createMeeting(body),
    );
    if (saved === undefined) return;
    setDrawerOpen(false);
    notifySuccess(editing ? 'Meeting updated' : 'Meeting scheduled', body.subject);
    reload();
  };

  const handleDelete = async (row: Meeting) => {
    const ok = await confirm({
      title: `Cancel "${row.subject}"?`,
      description:
        'The meeting is archived and leaves the calendar and the linked record timeline. Attendees are not notified — the CRM sends no invitations.',
      confirmLabel: 'Cancel meeting',
      cancelLabel: 'Keep meeting',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveMeeting(row.id);
      notifySuccess('Meeting cancelled', row.subject);
      reload();
    } catch (caught) {
      notifyError(caught, 'The meeting could not be cancelled.');
    }
  };

  const columns = useMemo<ColumnDef<Meeting>[]>(
    () => [
      { key: 'subject', label: 'Meeting', minWidth: '200px' },
      {
        key: 'start_time',
        label: 'Starts',
        render: (row) => (
          <span className="txt-muted text-[12.5px]">
            {formatWhen(meetingDetail(row)?.start_time)}
          </span>
        ),
      },
      {
        key: 'meeting_type',
        label: 'Type',
        hideBelow: 'md',
        render: (row) => {
          const detail = meetingDetail(row);
          return (
            <span className="txt-muted text-[12.5px]">
              {detail ? humanize(detail.meeting_type) : '—'}
            </span>
          );
        },
      },
      {
        key: 'related',
        label: 'Linked to',
        hideBelow: 'lg',
        render: (row) =>
          row.related_entity_type && row.related_entity_id ? (
            <span className="txt-muted text-[12.5px]">
              {related.label(row.related_entity_type, row.related_entity_id)}
            </span>
          ) : (
            <span className="txt-faint">—</span>
          ),
      },
      {
        key: 'status',
        label: 'Status',
        render: (row) => (
          <StatusBadge label={humanize(row.status)} variant={statusVariant(row.status)} />
        ),
      },
      {
        key: 'actions',
        label: '',
        align: 'right',
        render: (row) => (
          <div className="flex items-center justify-end gap-1">
            {mayEdit && (
              <button
                type="button"
                aria-label={`Edit ${row.subject}`}
                onClick={(event) => {
                  event.stopPropagation();
                  openEdit(row);
                }}
                className="ctl rounded-lg p-1.5 transition hover:opacity-70"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            )}
            {mayDelete && (
              <button
                type="button"
                aria-label={`Archive ${row.subject}`}
                onClick={(event) => {
                  event.stopPropagation();
                  void handleDelete(row);
                }}
                className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mayEdit, mayDelete, related],
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
            <CalendarDays className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Meetings</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Scheduled conversations, linked to the record they belong to.
            </p>
          </div>
        </div>
        {mayCreate && (
          <button
            type="button"
            onClick={openAdd}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <Plus className="h-4 w-4" /> Schedule meeting
          </button>
        )}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchInput
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder="Search meetings…"
        />
        <FilterSelect
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
          options={STATUS_OPTIONS}
        />
        {refreshing && (
          <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Refreshing" />
        )}
        <div className="ml-auto">
          <ResultCount shown={items.length} total={pagination?.total ?? 0} />
        </div>
      </div>

      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : (
        <DataTable
          columns={columns}
          data={items}
          rowKey={(row) => row.id}
          loading={status === 'loading'}
          skeletonRows={6}
          onRowClick={(row) => router.push(`/meetings/${row.id}`)}
          emptyState={
            <ListEmpty
              title="No meetings yet"
              hint={
                search || statusFilter
                  ? 'No meeting matches those filters.'
                  : 'Schedule a meeting and it will appear here and on the timeline of the record it is linked to.'
              }
            />
          }
        />
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit meeting' : 'Schedule meeting'}
        subtitle={editing ? editing.subject : 'Book a conversation against a CRM record.'}
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={pending || !form.subject.trim() || !form.start_time}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending ? 'Saving…' : 'Save'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <FormField label="Title" required>
            <FormInput
              value={form.subject}
              onChange={(event) => setForm({ ...form, subject: event.target.value })}
              placeholder="Proposal review"
            />
          </FormField>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Starts" required>
              <FormInput
                type="datetime-local"
                value={form.start_time}
                onChange={(event) => setForm({ ...form, start_time: event.target.value })}
              />
            </FormField>
            <FormField label="Ends">
              <FormInput
                type="datetime-local"
                value={form.end_time}
                onChange={(event) => setForm({ ...form, end_time: event.target.value })}
              />
            </FormField>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Format">
              <FormSelect
                value={form.meeting_type}
                onChange={(event) =>
                  setForm({ ...form, meeting_type: event.target.value as MeetingType })
                }
                options={MEETING_TYPES.map((value) => ({ value, label: humanize(value) }))}
              />
            </FormField>
            <FormField label="Status">
              <FormSelect
                value={form.status}
                onChange={(event) =>
                  setForm({ ...form, status: event.target.value as ActivityStatus })
                }
                options={MEETING_STATUSES.map((value) => ({ value, label: humanize(value) }))}
              />
            </FormField>
          </div>

          <FormField label="Location">
            <FormInput
              value={form.location}
              onChange={(event) => setForm({ ...form, location: event.target.value })}
              placeholder="Room 4, or the city for an in-person meeting"
            />
          </FormField>

          <FormField label="Joining link">
            <FormInput
              type="url"
              value={form.meeting_link}
              onChange={(event) => setForm({ ...form, meeting_link: event.target.value })}
              placeholder="https://…"
            />
          </FormField>

          <RelatedRecordFields
            options={related}
            entityType={form.related_entity_type}
            entityId={form.related_entity_id}
            onChange={(entityType, entityId) =>
              setForm({ ...form, related_entity_type: entityType, related_entity_id: entityId })
            }
          />

          <FormField label="Agenda">
            <FormTextarea
              value={form.agenda}
              onChange={(event) => setForm({ ...form, agenda: event.target.value })}
              rows={3}
            />
          </FormField>

          <FormField label="Notes">
            <FormTextarea
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              rows={2}
            />
          </FormField>

          <FormError message={validation ?? saveError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
