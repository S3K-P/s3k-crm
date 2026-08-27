'use client';

import { useCallback, useMemo, useState } from 'react';
import { ClipboardList, Plus, Pencil, Trash2, Loader2, Check } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
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
  CLOSED_TASK_STATUSES,
  TASK_PRIORITIES,
  TASK_STATUSES,
  archiveTask,
  changeTaskStatus,
  createTask,
  listTasks,
  updateTask,
  type Priority,
  type Task,
  type TaskInput,
  type TaskStatus,
} from '@/features/crm/tasks';

/* ============================================================
   TASKS

   The route the plan calls for at W18-FE-02, which did not
   previously exist. Rows come from `GET /api/v1/crm/tasks`.

   `completed_at` is derived by the backend from the status, so
   the tick button posts a status change rather than trying to
   set a timestamp the server owns.

   A task can be attached to an account, contact, lead,
   opportunity or campaign. The schema, the API and the wire type
   all supported that from the start; the form did not offer it,
   so every task created here was orphaned and appeared on no
   record's timeline. That is what `RelatedRecordFields` fixes.
   ============================================================ */

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...TASK_STATUSES.map((value) => ({ value, label: humanize(value) })),
];

const PRIORITY_FILTER_OPTIONS = [
  { value: '', label: 'All priorities' },
  ...TASK_PRIORITIES.map((value) => ({ value, label: humanize(value) })),
];

const EMPTY_FORM: TaskInput = {
  title: '',
  description: '',
  status: 'PENDING',
  priority: 'MEDIUM',
  due_date: '',
  related_entity_type: null,
  related_entity_id: null,
};

/** `datetime-local` needs "YYYY-MM-DDTHH:mm"; the API returns ISO-8601. */
function toLocalInput(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDue(iso: string | null): string {
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

export default function TasksPage() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('tasks', 'CREATE');
  const mayEdit = can('tasks', 'EDIT');
  const mayDelete = can('tasks', 'DELETE');

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () =>
      listTasks({
        page,
        page_size: 25,
        search: search.trim() || null,
        status: (statusFilter || null) as TaskStatus | null,
        priority: (priorityFilter || null) as Priority | null,
        sort_by: 'due_date',
        sort_dir: 'asc',
      }),
    [page, search, statusFilter, priorityFilter],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Task>(
    fetcher,
    [page, search, statusFilter, priorityFilter],
    { errorMessage: 'Something went wrong loading tasks.' },
  );

  const related = useRelatedRecordOptions();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [form, setForm] = useState<TaskInput>(EMPTY_FORM);
  const { pending, error: saveError, clearError, run } = useMutation();

  const openAdd = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: Task) => {
    setEditing(row);
    setForm({
      title: row.title,
      description: row.description ?? '',
      status: row.status,
      priority: row.priority,
      due_date: toLocalInput(row.due_date),
      related_entity_type: row.related_entity_type,
      related_entity_id: row.related_entity_id,
    });
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    if (!form.title.trim()) return;
    const body: TaskInput = {
      title: form.title.trim(),
      description: form.description?.trim() || null,
      status: form.status,
      priority: form.priority,
      // An empty input means "no due date", not "the epoch".
      due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
      // Both halves of the polymorphic link travel together or not at all:
      // the backend rejects a type without an id.
      related_entity_type: form.related_entity_id ? (form.related_entity_type ?? null) : null,
      related_entity_id: form.related_entity_id || null,
    };
    const saved = await run(() =>
      editing ? updateTask(editing.id, body) : createTask(body),
    );
    if (saved === undefined) return;
    setDrawerOpen(false);
    notifySuccess(editing ? 'Task updated' : 'Task created', body.title);
    reload();
  };

  /* Completing is cheap and reversible from the same control, so it is not
     confirmed — it only has to report what it did. */
  const handleComplete = async (row: Task) => {
    const next: TaskStatus = row.status === 'COMPLETED' ? 'PENDING' : 'COMPLETED';
    try {
      await changeTaskStatus(row.id, next);
      notifySuccess(next === 'COMPLETED' ? 'Task completed' : 'Task reopened', row.title);
      reload();
    } catch (caught) {
      notifyError(caught, 'The task status could not be changed.');
    }
  };

  const handleDelete = async (row: Task) => {
    const ok = await confirm({
      title: `Archive "${row.title}"?`,
      description:
        'The task leaves the task list and the timeline of the record it is linked to.',
      confirmLabel: 'Archive task',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveTask(row.id);
      notifySuccess('Task archived', row.title);
      reload();
    } catch (caught) {
      notifyError(caught, 'The task could not be archived.');
    }
  };

  const columns = useMemo<ColumnDef<Task>[]>(
    () => [
      {
        key: 'title',
        label: 'Task',
        minWidth: '220px',
        render: (row) => (
          <span
            className={
              CLOSED_TASK_STATUSES.includes(row.status) ? 'txt-faint line-through' : ''
            }
          >
            {row.title}
          </span>
        ),
      },
      {
        key: 'due_date',
        label: 'Due',
        hideBelow: 'md',
        render: (row) => <span className="tabular-nums">{formatDue(row.due_date)}</span>,
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
        key: 'priority',
        label: 'Priority',
        hideBelow: 'lg',
        render: (row) => (
          <StatusBadge label={humanize(row.priority)} variant={statusVariant(row.priority)} />
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
              <>
                <button
                  type="button"
                  aria-label={
                    row.status === 'COMPLETED' ? `Reopen ${row.title}` : `Complete ${row.title}`
                  }
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleComplete(row);
                  }}
                  className="ctl rounded-lg p-1.5 text-emerald-600 transition hover:opacity-70"
                >
                  <Check className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  aria-label={`Edit ${row.title}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    openEdit(row);
                  }}
                  className="ctl rounded-lg p-1.5 transition hover:opacity-70"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              </>
            )}
            {mayDelete && (
              <button
                type="button"
                aria-label={`Archive ${row.title}`}
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
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-500 to-purple-600">
            <ClipboardList className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Tasks</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Work to be done, with due dates the dashboard counts.
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
            <Plus className="h-4 w-4" /> New task
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
          placeholder="Search tasks…"
        />
        <FilterSelect
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
          options={STATUS_FILTER_OPTIONS}
        />
        <FilterSelect
          value={priorityFilter}
          onChange={(event) => {
            setPriorityFilter(event.target.value);
            setPage(1);
          }}
          options={PRIORITY_FILTER_OPTIONS}
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
          emptyState={
            <ListEmpty
              title="No tasks yet"
              hint={
                search || statusFilter || priorityFilter
                  ? 'No task matches those filters.'
                  : 'Tasks you create appear here and in the dashboard’s “Tasks due” count.'
              }
            />
          }
        />
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit task' : 'New task'}
        subtitle={editing ? editing.title : 'Add something that needs doing.'}
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
              disabled={pending || !form.title.trim()}
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
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="Follow up with…"
            />
          </FormField>
          <FormField label="Due">
            <FormInput
              type="datetime-local"
              value={form.due_date ?? ''}
              onChange={(event) => setForm({ ...form, due_date: event.target.value })}
            />
          </FormField>
          <FormField label="Priority">
            <FormSelect
              value={form.priority ?? 'MEDIUM'}
              onChange={(event) =>
                setForm({ ...form, priority: event.target.value as Priority })
              }
              options={TASK_PRIORITIES.map((value) => ({ value, label: humanize(value) }))}
            />
          </FormField>
          <FormField label="Status">
            <FormSelect
              value={form.status ?? 'PENDING'}
              onChange={(event) =>
                setForm({ ...form, status: event.target.value as TaskStatus })
              }
              options={TASK_STATUSES.map((value) => ({ value, label: humanize(value) }))}
            />
          </FormField>
          <RelatedRecordFields
            options={related}
            entityType={form.related_entity_type ?? ''}
            entityId={form.related_entity_id ?? ''}
            onChange={(entityType, entityId) =>
              setForm({
                ...form,
                related_entity_type: entityType || null,
                related_entity_id: entityId || null,
              })
            }
          />
          <FormField label="Description">
            <FormTextarea
              value={form.description ?? ''}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              rows={3}
            />
          </FormField>
          <FormError message={saveError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
