'use client';

import { useCallback, useMemo, useState } from 'react';
import { Globe, Plus, Pencil, Trash2, Loader2 } from 'lucide-react';

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
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import {
  archiveLeadSource,
  createLeadSource,
  listLeadSources,
  updateLeadSource,
  type LeadSource,
  type LeadSourceInput,
  type LeadSourceStatus,
} from '@/features/crm/lead-sources';

/* ============================================================
   LEAD SOURCES

   Every row comes from `GET /api/v1/crm/lead-sources`, scoped by
   the backend to the signed-in user's organization. Creating,
   editing and archiving all round-trip to the API, so what the
   table shows survives a refresh, a sign-out and a new session.

   `lead_count` is computed by the backend from the leads table,
   not stored, so it cannot drift from reality.
   ============================================================ */

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'ACTIVE', label: 'Active' },
  { value: 'INACTIVE', label: 'Inactive' },
];

const EMPTY_FORM: LeadSourceInput = {
  name: '',
  category: '',
  description: '',
  status: 'ACTIVE',
};

export default function LeadSourcesPage() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('lead_sources', 'CREATE');
  const mayEdit = can('lead_sources', 'EDIT');
  const mayDelete = can('lead_sources', 'DELETE');

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () =>
      listLeadSources({
        page,
        page_size: 25,
        search: search.trim() || null,
        status: (statusFilter || null) as LeadSourceStatus | null,
        sort_by: 'name',
        sort_dir: 'asc',
      }),
    [page, search, statusFilter],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<LeadSource>(
    fetcher,
    [page, search, statusFilter],
    { errorMessage: 'Something went wrong loading lead sources.' },
  );

  /* ---- Drawer ---- */
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<LeadSource | null>(null);
  const [form, setForm] = useState<LeadSourceInput>(EMPTY_FORM);
  const { pending, error: saveError, clearError, run } = useMutation();

  const openAdd = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: LeadSource) => {
    setEditing(row);
    setForm({
      name: row.name,
      category: row.category ?? '',
      description: row.description ?? '',
      status: row.status,
    });
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    const body: LeadSourceInput = {
      name: form.name.trim(),
      category: form.category?.trim() || null,
      description: form.description?.trim() || null,
      status: form.status,
    };
    const saved = await run(() =>
      editing ? updateLeadSource(editing.id, body) : createLeadSource(body),
    );
    if (saved === undefined) return; // the drawer stays open and shows the error
    setDrawerOpen(false);
    notifySuccess(editing ? 'Lead source updated' : 'Lead source created', body.name);
    reload();
  };

  const handleDelete = async (row: LeadSource) => {
    const ok = await confirm({
      title: `Archive ${row.name}?`,
      description:
        'It stops being offered when creating a lead. Leads and opportunities already attributed to it keep the attribution, so source reporting stays intact.',
      confirmLabel: 'Archive source',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveLeadSource(row.id);
      notifySuccess('Lead source archived', row.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The lead source could not be archived.');
    }
  };

  const columns = useMemo<ColumnDef<LeadSource>[]>(
    () => [
      { key: 'name', label: 'Source', minWidth: '180px' },
      {
        key: 'category',
        label: 'Category',
        hideBelow: 'md',
        render: (row) => row.category ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'lead_count',
        label: 'Leads',
        align: 'right',
        render: (row) => <span className="tabular-nums">{row.lead_count}</span>,
      },
      {
        key: 'status',
        label: 'Status',
        render: (row) => <StatusBadge label={humanize(row.status)} variant={statusVariant(row.status)} />,
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
                aria-label={`Edit ${row.name}`}
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
                aria-label={`Archive ${row.name}`}
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
    // `handleDelete` is recreated each render but closes over nothing that
    // changes the column shape.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mayEdit, mayDelete],
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
            <Globe className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Lead Sources</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Where your leads come from, and how many each has produced.
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
            <Plus className="h-4 w-4" /> New source
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
          placeholder="Search sources…"
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
          emptyState={
            <ListEmpty
              title="No lead sources yet"
              hint={
                search || statusFilter
                  ? 'No source matches those filters.'
                  : 'Add the channels your leads arrive through, and this table will track each one.'
              }
            />
          }
        />
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit lead source' : 'New lead source'}
        subtitle={editing ? editing.name : 'Add a channel that produces leads.'}
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
              disabled={pending || !form.name.trim()}
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
          <FormField label="Name" required>
            <FormInput
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Website, Referral, Trade show…"
            />
          </FormField>
          <FormField label="Category">
            <FormInput
              value={form.category ?? ''}
              onChange={(event) => setForm({ ...form, category: event.target.value })}
              placeholder="Inbound, Outbound, Partner…"
            />
          </FormField>
          <FormField label="Status">
            <FormSelect
              value={form.status ?? 'ACTIVE'}
              onChange={(event) =>
                setForm({ ...form, status: event.target.value as LeadSourceStatus })
              }
              options={[
                { value: 'ACTIVE', label: 'Active' },
                { value: 'INACTIVE', label: 'Inactive' },
              ]}
            />
          </FormField>
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
