'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Users, Plus, Pencil, Trash2, Loader2, LayoutList, LayoutGrid,
} from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import KanbanBoard, { type KanbanColumnDef } from '@/components/crm/kanban/KanbanBoard';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import { listLeadSources, type LeadSource } from '@/features/crm/lead-sources';
import {
  LEAD_STATUSES,
  PRIORITIES,
  archiveLead,
  changeLeadStatus,
  createLead,
  listLeads,
  updateLead,
  type Lead,
  type LeadInput,
  type LeadStatus,
  type Priority,
} from '@/features/crm/leads';

/* ============================================================
   LEADS

   Rows come from `GET /api/v1/crm/leads`. The kanban moves a
   lead with `POST /crm/leads/{id}/status`, which is the only
   path that enforces the transition state machine — an illegal
   move returns 422 and the board reverts rather than showing a
   change the database refused.

   CONVERTED is never settable here: conversion goes through
   `POST /crm/leads/{id}/convert` on the detail page, because it
   creates an account and a contact in the same transaction.
   ============================================================ */

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...LEAD_STATUSES.map((value) => ({ value, label: humanize(value) })),
];

const KANBAN_COLUMNS: KanbanColumnDef<Lead>[] = LEAD_STATUSES.map((status) => ({
  id: status,
  label: humanize(status),
  color:
    status === 'CONVERTED'
      ? '#059669'
      : status === 'LOST'
        ? '#dc2626'
        : 'var(--accent)',
}));

const EMPTY_FORM: LeadInput = {
  first_name: '',
  last_name: '',
  company: '',
  email: '',
  phone: '',
  priority: 'MEDIUM',
  lead_source_id: '',
  notes: '',
};

type ViewMode = 'table' | 'kanban';

export default function LeadsPage() {
  const router = useRouter();
  const { can } = usePermissions();
  const mayCreate = can('leads', 'CREATE');
  const mayEdit = can('leads', 'EDIT');
  const mayDelete = can('leads', 'DELETE');
  const mayViewSources = can('lead_sources', 'VIEW');

  const [view, setView] = useState<ViewMode>('table');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  // The board needs every lead at once; the table is paginated.
  const pageSize = view === 'kanban' ? 200 : 25;

  const fetcher = useCallback(
    () =>
      listLeads({
        page: view === 'kanban' ? 1 : page,
        page_size: pageSize,
        search: search.trim() || null,
        status: (statusFilter || null) as LeadStatus | null,
        sort_by: 'created_at',
        sort_dir: 'desc',
      }),
    [page, pageSize, search, statusFilter, view],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Lead>(
    fetcher,
    [page, pageSize, search, statusFilter, view],
    { errorMessage: 'Something went wrong loading leads.' },
  );

  const [sources, setSources] = useState<LeadSource[]>([]);
  useEffect(() => {
    if (!mayViewSources) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await listLeadSources({ page_size: 200, status: 'ACTIVE' });
        if (!cancelled) setSources(result.data);
      } catch {
        // Non-fatal — the picker is simply empty.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewSources]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Lead | null>(null);
  const [form, setForm] = useState<LeadInput>(EMPTY_FORM);
  const { pending, error: saveError, clearError, run } = useMutation();
  const [boardError, setBoardError] = useState<string | null>(null);

  const openAdd = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: Lead) => {
    setEditing(row);
    setForm({
      first_name: row.first_name,
      last_name: row.last_name,
      company: row.company ?? '',
      email: row.email ?? '',
      phone: row.phone ?? '',
      priority: row.priority ?? 'MEDIUM',
      lead_source_id: row.lead_source_id ?? '',
      notes: row.notes ?? '',
    });
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    if (!form.first_name.trim() || !form.last_name.trim()) return;
    const body: LeadInput = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      company: form.company?.trim() || null,
      email: form.email?.trim() || null,
      phone: form.phone?.trim() || null,
      priority: form.priority,
      lead_source_id: form.lead_source_id || null,
      notes: form.notes?.trim() || null,
    };
    const saved = await run(() =>
      editing ? updateLead(editing.id, body) : createLead(body),
    );
    if (saved === undefined) return;
    setDrawerOpen(false);
    reload();
  };

  const handleDelete = async (row: Lead) => {
    const done = await run(() => archiveLead(row.id));
    if (done !== undefined) reload();
  };

  const handleStatusChange = async (row: Lead, next: LeadStatus) => {
    setBoardError(null);
    try {
      await changeLeadStatus(row.id, next);
      reload();
    } catch (caught) {
      // The backend rejected the transition. Say so and reload, so the board
      // shows what the database actually holds rather than the attempted move.
      setBoardError(
        caught instanceof Error
          ? caught.message
          : 'That status change is not allowed from the current status.',
      );
      reload();
    }
  };

  const columns = useMemo<ColumnDef<Lead>[]>(
    () => [
      {
        key: 'first_name',
        label: 'Name',
        minWidth: '170px',
        render: (row) => `${row.first_name} ${row.last_name}`,
      },
      {
        key: 'company',
        label: 'Company',
        hideBelow: 'md',
        render: (row) => row.company ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'email',
        label: 'Email',
        hideBelow: 'lg',
        render: (row) => row.email ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'priority',
        label: 'Priority',
        hideBelow: 'xl',
        render: (row) =>
          row.priority ? (
            <StatusBadge label={humanize(row.priority)} variant={statusVariant(row.priority)} />
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
                aria-label={`Edit ${row.first_name} ${row.last_name}`}
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
                aria-label={`Archive ${row.first_name} ${row.last_name}`}
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
    [mayEdit, mayDelete],
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-emerald-500 to-green-600">
            <Users className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Leads</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Prospects moving toward becoming customers.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="ctl bd flex items-center rounded-lg border p-0.5">
            <button
              type="button"
              aria-label="Table view"
              aria-pressed={view === 'table'}
              onClick={() => setView('table')}
              className={`rounded-md p-1.5 transition ${view === 'table' ? 'bg-[var(--surface-2)]' : 'opacity-60'}`}
            >
              <LayoutList className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="Board view"
              aria-pressed={view === 'kanban'}
              onClick={() => setView('kanban')}
              className={`rounded-md p-1.5 transition ${view === 'kanban' ? 'bg-[var(--surface-2)]' : 'opacity-60'}`}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>
          {mayCreate && (
            <button
              type="button"
              onClick={openAdd}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              <Plus className="h-4 w-4" /> New lead
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchInput
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder="Search name, company or email…"
        />
        <FilterSelect
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
          options={STATUS_FILTER_OPTIONS}
        />
        {refreshing && (
          <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Refreshing" />
        )}
        <div className="ml-auto">
          <ResultCount shown={items.length} total={pagination?.total ?? 0} />
        </div>
      </div>

      {boardError && (
        <p role="alert" className="text-[12.5px] font-medium text-red-500">
          {boardError}
        </p>
      )}

      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : view === 'table' ? (
        <DataTable
          columns={columns}
          data={items}
          rowKey={(row) => row.id}
          onRowClick={(row) => router.push(`/leads/${row.id}`)}
          loading={status === 'loading'}
          skeletonRows={6}
          emptyState={
            <ListEmpty
              title="No leads yet"
              hint={
                search || statusFilter
                  ? 'No lead matches those filters.'
                  : 'Create your first lead and it will appear here and on the dashboard.'
              }
            />
          }
        />
      ) : status === 'loading' ? (
        <div className="txt-muted flex items-center gap-2 py-12 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading board…
        </div>
      ) : (
        <KanbanBoard
          columns={KANBAN_COLUMNS}
          data={items}
          groupBy={(lead) => lead.status}
          renderCard={(lead) => (
            <div className="surface bd rounded-xl border p-3">
              <button
                type="button"
                onClick={() => router.push(`/leads/${lead.id}`)}
                className="txt block text-left text-[13.5px] font-semibold hover:opacity-70"
              >
                {lead.first_name} {lead.last_name}
              </button>
              {lead.company && (
                <p className="txt-muted mt-0.5 text-[12px]">{lead.company}</p>
              )}
              {mayEdit && (
                <FilterSelect
                  className="mt-2 w-full"
                  value={lead.status}
                  onChange={(event) =>
                    void handleStatusChange(lead, event.target.value as LeadStatus)
                  }
                  aria-label={`Change status for ${lead.first_name} ${lead.last_name}`}
                  options={LEAD_STATUSES.map((value) => ({
                    value,
                    label: humanize(value),
                  }))}
                />
              )}
            </div>
          )}
        />
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit lead' : 'New lead'}
        subtitle={
          editing
            ? `${editing.first_name} ${editing.last_name}`
            : 'Leads always start at New.'
        }
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
              disabled={pending || !form.first_name.trim() || !form.last_name.trim()}
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
          <div className="grid grid-cols-2 gap-3">
            <FormField label="First name" required>
              <FormInput
                value={form.first_name}
                onChange={(event) => setForm({ ...form, first_name: event.target.value })}
              />
            </FormField>
            <FormField label="Last name" required>
              <FormInput
                value={form.last_name}
                onChange={(event) => setForm({ ...form, last_name: event.target.value })}
              />
            </FormField>
          </div>
          <FormField label="Company">
            <FormInput
              value={form.company ?? ''}
              onChange={(event) => setForm({ ...form, company: event.target.value })}
            />
          </FormField>
          <FormField label="Email">
            <FormInput
              type="email"
              value={form.email ?? ''}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </FormField>
          <FormField label="Phone">
            <FormInput
              value={form.phone ?? ''}
              onChange={(event) => setForm({ ...form, phone: event.target.value })}
            />
          </FormField>
          <FormField label="Priority">
            <FormSelect
              value={form.priority ?? 'MEDIUM'}
              onChange={(event) =>
                setForm({ ...form, priority: event.target.value as Priority })
              }
              options={PRIORITIES.map((value) => ({ value, label: humanize(value) }))}
            />
          </FormField>
          <FormField label="Lead source">
            <FormSelect
              value={form.lead_source_id ?? ''}
              onChange={(event) => setForm({ ...form, lead_source_id: event.target.value })}
              placeholder="No source"
              disabled={!mayViewSources}
              options={sources.map((source) => ({ value: source.id, label: source.name }))}
            />
          </FormField>
          <FormField label="Notes">
            <FormTextarea
              value={form.notes ?? ''}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              rows={3}
            />
          </FormField>
          <FormError message={saveError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
