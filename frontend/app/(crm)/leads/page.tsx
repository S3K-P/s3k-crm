'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Users, Plus, Pencil, Trash2, Loader2, LayoutList, LayoutGrid, Upload, GitMerge,
} from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import KanbanBoard, { type KanbanColumnDef } from '@/components/crm/kanban/KanbanBoard';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess, notifyWarning } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import MergeDialog from '@/components/crm/dialogs/MergeDialog';
import BulkActionsToolbar, { type BulkEditableField } from '@/components/crm/toolbar/BulkActionsToolbar';
import ColumnChooser, { type ColumnOption } from '@/components/crm/toolbar/ColumnChooser';
import SavedViewPicker from '@/components/crm/toolbar/SavedViewPicker';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import ImportWizard from '@/components/crm/import/ImportWizard';
import ExportButton from '@/components/crm/toolbar/ExportButton';
import CustomFieldInputs from '@/components/crm/forms/CustomFieldInputs';
import { changedValues, type CustomFieldValues } from '@/features/crm/custom-fields';
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import { useQueryFilter } from '@/features/shared/hooks/useQueryFilter';
import { listLeadSources, type LeadSource } from '@/features/crm/lead-sources';
import { listCampaigns, type Campaign } from '@/features/crm/campaigns';
import { listMembers, type OrganizationMember } from '@/features/admin/users';
import {
  LEAD_STATUSES,
  PRIORITIES,
  archiveLead,
  bulkChangeLeadStatus,
  bulkDeleteLeads,
  bulkUpdateLeads,
  changeLeadStatus,
  createLead,
  exportLeads,
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

const KANBAN_COLUMNS: KanbanColumnDef[] = LEAD_STATUSES.map((status) => ({
  id: status,
  label: humanize(status),
  color:
    status === 'CONVERTED'
      ? '#059669'
      : status === 'LOST' || status === 'UNQUALIFIED'
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
  owner_id: '',
  lead_source_id: '',
  campaign_id: '',
  industry: '',
  website: '',
  company_size: '',
  product_interest: '',
  expected_deal_size: '',
  notes: '',
};

type ViewMode = 'table' | 'kanban';

/** Optional columns a user may hide (Checkpoint 4) — name and actions always show. */
const OPTIONAL_COLUMNS: ColumnOption[] = [
  { key: 'company', label: 'Company' },
  { key: 'email', label: 'Email' },
  { key: 'priority', label: 'Priority' },
  { key: 'status', label: 'Status' },
];
const OPTIONAL_COLUMN_KEYS = OPTIONAL_COLUMNS.map((c) => c.key);

export default function LeadsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('leads', 'CREATE');
  const mayExport = can('leads', 'EXPORT');
  const [importOpen, setImportOpen] = useState(false);
  const mayEdit = can('leads', 'EDIT');
  const mayDelete = can('leads', 'DELETE');
  // Merging is an edit *and* a deletion, so the control is offered only to
  // somebody holding both — the same pair the endpoint demands. Hiding it
  // protects nothing on its own; it stops offering a button that would 403.
  const mayMerge = mayEdit && mayDelete;
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [mergeOpen, setMergeOpen] = useState(false);
  const [bulkStatusOpen, setBulkStatusOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState<string[]>(OPTIONAL_COLUMN_KEYS);
  const mayViewSources = can('lead_sources', 'VIEW');
  const mayViewCampaigns = can('campaigns', 'VIEW');
  const mayViewMembers = can('users', 'VIEW');

  const [view, setView] = useState<ViewMode>('table');
  const [search, setSearch] = useState('');
  // `/leads?status=NEW` and `?status=QUALIFIED` are where the dashboard's lead
  // tiles point: the tile counts a status, so the link opens that status.
  const [statusFilter, setStatusFilter] = useState<string>(
    useQueryFilter('status', LEAD_STATUSES),
  );
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

  const [members, setMembers] = useState<OrganizationMember[]>([]);
  useEffect(() => {
    if (!mayViewMembers) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await listMembers();
        if (!cancelled) {
          setMembers(result.data.filter((member) => member.status === 'ACTIVE'));
        }
      } catch {
        // Non-fatal — owner picker stays empty.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewMembers]);

  /* Campaigns, for attribution on a new lead. Only the ones still running are
     offered: attributing a fresh lead to a completed campaign is almost always
     a mis-click rather than an intention. */
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  useEffect(() => {
    if (!mayViewCampaigns) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await listCampaigns({ page_size: 200 });
        if (!cancelled) {
          setCampaigns(
            result.data.filter(
              (campaign) => campaign.status === 'ACTIVE' || campaign.status === 'PLANNING',
            ),
          );
        }
      } catch {
        // Non-fatal — the picker is simply empty.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewCampaigns]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  // Custom values are held apart from `form` because they are keyed by tenant
  // data: folding them into a typed `LeadInput` would mean giving that
  // interface an index signature, and losing every check on the real columns.
  const [customValues, setCustomValues] = useState<CustomFieldValues>({});
  const [editing, setEditing] = useState<Lead | null>(null);
  const [form, setForm] = useState<LeadInput>(EMPTY_FORM);
  const [duplicateWarning, setDuplicateWarning] = useState(false);
  const { pending, error: saveError, clearError, run } = useMutation();
  const [boardError, setBoardError] = useState<string | null>(null);

  const openAdd = () => {
    setCustomValues({});
    setEditing(null);
    setForm(EMPTY_FORM);
    setDuplicateWarning(false);
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: Lead) => {
    setCustomValues(row.custom_fields ?? {});
    setEditing(row);
    setForm({
      first_name: row.first_name,
      last_name: row.last_name,
      company: row.company ?? '',
      email: row.email ?? '',
      phone: row.phone ?? '',
      priority: row.priority ?? 'MEDIUM',
      owner_id: row.owner_id ?? '',
      lead_source_id: row.lead_source_id ?? '',
      industry: row.industry ?? '',
      website: row.website ?? '',
      company_size: row.company_size ?? '',
      product_interest: row.product_interest ?? '',
      expected_deal_size: row.expected_deal_size ?? '',
      notes: row.notes ?? '',
    });
    setDuplicateWarning(false);
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async (allowDuplicate = false) => {
    if (!form.first_name.trim() || !form.last_name.trim()) return;
    const body: LeadInput = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      company: form.company?.trim() || null,
      email: form.email?.trim() || null,
      phone: form.phone?.trim() || null,
      priority: form.priority,
      owner_id: form.owner_id || null,
      lead_source_id: form.lead_source_id || null,
      industry: form.industry?.trim() || null,
      website: form.website?.trim() || null,
      company_size: form.company_size?.trim() || null,
      product_interest: form.product_interest?.trim() || null,
      expected_deal_size: form.expected_deal_size || null,
      notes: form.notes?.trim() || null,
      // Only what the user actually touched. Sending the whole document would
      // be harmless but noisy; sending `{}` when they touched nothing would
      // *clear* every custom value on the record.
      ...(Object.keys(changedValues(customValues, editing?.custom_fields)).length > 0
        ? { custom_fields: changedValues(customValues, editing?.custom_fields) }
        : {}),
    };
    // Campaign attribution is create-only: `LeadUpdate` does not accept it,
    // so sending it on an edit would be silently discarded.
    if (!editing && form.campaign_id) body.campaign_id = form.campaign_id;
    const saved = await run(() =>
      editing ? updateLead(editing.id, body) : createLead(body, allowDuplicate),
    );
    if (saved === undefined) {
      // A duplicate email is a warning, not a hard rejection: offer the
      // override rather than forcing the user to invent a second address.
      if (!editing && !allowDuplicate) {
        setDuplicateWarning(true);
        notifyWarning(
          'A lead with that email already exists',
          'Press "Save anyway" to create a second record for the same address.',
        );
      }
      return;
    }
    setDrawerOpen(false);
    setDuplicateWarning(false);
    notifySuccess(
      editing ? 'Lead updated' : 'Lead created',
      `${body.first_name} ${body.last_name}`,
    );
    reload();
  };

  const handleDelete = async (row: Lead) => {
    const name = `${row.first_name} ${row.last_name}`;
    const ok = await confirm({
      title: `Archive ${name}?`,
      description:
        'The lead is soft-deleted: it disappears from lists and reports but its activities and notes are kept. Ask an administrator to restore it if this was a mistake.',
      confirmLabel: 'Archive lead',
      tone: 'danger',
    });
    if (!ok) return;
    // Deliberately not routed through `run`: that hook feeds the drawer's
    // inline FormError, which is not on screen for a row action. Here the
    // toast is the only channel, so the backend's own message must reach it.
    try {
      await archiveLead(row.id);
      notifySuccess('Lead archived', name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The lead could not be archived.');
    }
  };

  const handleStatusChange = async (row: Lead, next: LeadStatus) => {
    setBoardError(null);
    try {
      await changeLeadStatus(row.id, next);
      notifySuccess(
        'Status updated',
        `${row.first_name} ${row.last_name} → ${humanize(next)}`,
      );
      reload();
    } catch (caught) {
      // The backend rejected the transition. Say so and reload, so the board
      // shows what the database actually holds rather than the attempted move.
      setBoardError(
        caught instanceof Error
          ? caught.message
          : 'That status change is not allowed from the current status.',
      );
      notifyError(caught, 'That status change is not allowed from the current status.');
      reload();
    }
  };

  const bulkFields = useMemo<BulkEditableField[]>(
    () => [
      {
        key: 'priority',
        label: 'Priority',
        type: 'select',
        options: PRIORITIES.map((p) => ({ value: p, label: humanize(p) })),
      },
      { key: 'industry', label: 'Industry' },
      { key: 'company_size', label: 'Company size' },
      {
        key: 'owner_id',
        label: 'Owner',
        type: 'select',
        options: members.map((member) => ({
          value: member.user_id,
          label: member.full_name?.trim() || member.email,
        })),
      },
    ],
    [members],
  );

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
        editable: () => mayEdit,
        editType: 'email',
        render: (row) => row.email ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'priority',
        label: 'Priority',
        hideBelow: 'xl',
        editable: () => mayEdit,
        editType: 'select',
        editOptions: PRIORITIES.map((p) => ({ value: p, label: humanize(p) })),
        editValue: (row) => row.priority ?? '',
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
        <SavedViewPicker
          entityType="LEAD"
          current={{ search: search.trim() || null, status: statusFilter || null }}
          onApply={(params) => {
            // A view carries filters only; the screen owns its own state, so
            // applying one means setting that state rather than short-
            // circuiting the fetch. Anything the view does not mention is
            // cleared, so switching views cannot leave a stale filter behind.
            setSearch(typeof params.search === 'string' ? params.search : '');
            setStatusFilter(typeof params.status === 'string' ? params.status : '');
            setPage(1);
          }}
          columns={visibleColumns}
          onColumnsChange={setVisibleColumns}
        />
        {view === 'table' && (
          <ColumnChooser
            options={OPTIONAL_COLUMNS}
            visible={visibleColumns}
            onChange={setVisibleColumns}
          />
        )}
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
        {mayCreate && (
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            className="ctl flex items-center gap-2 px-3 py-2 text-[13px] font-semibold transition hover:opacity-80"
          >
            <Upload className="h-4 w-4" aria-hidden="true" /> Import CSV
          </button>
        )}
        {mayExport && (
          <ExportButton
            entityPlural="leads"
            count={pagination?.total}
            onExport={() =>
              exportLeads({
                search: search.trim() || null,
                status: (statusFilter || null) as LeadStatus | null,
              })
            }
          />
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

      <ImportWizard
        open={importOpen}
        onClose={() => setImportOpen(false)}
        slug="leads"
        onImported={reload}
      />

      {(mayEdit || mayDelete) && selectedIds.size > 0 && (
        <div className="mb-3">
          <BulkActionsToolbar
            count={selectedIds.size}
            onClear={() => setSelectedIds(new Set())}
            mayEdit={mayEdit}
            mayDelete={mayDelete}
            entityLabelPlural="leads"
            editableFields={bulkFields}
            onBulkUpdate={(values) => bulkUpdateLeads(Array.from(selectedIds), values)}
            onBulkDelete={() => bulkDeleteLeads(Array.from(selectedIds))}
            onDone={() => {
              setSelectedIds(new Set());
              reload();
            }}
            extraActions={
              <>
                {mayEdit && (
                  <button
                    type="button"
                    onClick={() => setBulkStatusOpen(true)}
                    className="txt-accent text-[12.5px] font-medium"
                  >
                    Bulk status change
                  </button>
                )}
                {mayMerge && mergeCandidates(items, selectedIds).length > 1 && (
                  <button
                    type="button"
                    onClick={() => setMergeOpen(true)}
                    className="flex items-center gap-1.5 text-[12.5px] font-medium"
                    style={{ color: 'var(--accent)' }}
                  >
                    <GitMerge className="h-3.5 w-3.5" /> Merge duplicates
                  </button>
                )}
              </>
            }
          />
        </div>
      )}
      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : view === 'table' ? (
        <DataTable
          columns={columns.filter((c) => !OPTIONAL_COLUMN_KEYS.includes(c.key) || visibleColumns.includes(c.key))}
          data={items}
          rowKey={(row) => row.id}
          onRowClick={(row) => router.push(`/leads/${row.id}`)}
          loading={status === 'loading'}
          skeletonRows={6}
          selectable={mayEdit || mayDelete}
          selectedKeys={selectedIds}
          onSelectionChange={setSelectedIds}
          onCellEdit={async (row, key, value) => {
            await updateLead(row.id, { [key]: value } as Partial<LeadInput>);
            reload();
          }}
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
          getItemId={(lead) => lead.id}
          canDrag={(lead) => mayEdit && lead.status !== 'CONVERTED'}
          // Dropping a card posts through the identical `/leads/{id}/status`
          // endpoint the per-card select already uses, so the same state
          // machine that rejects an illegal move there rejects it here —
          // dragging is a different gesture for the same request, not a
          // shortcut around it.
          // Returning the promise (not `void`-wrapping it) is what lets
          // KanbanBoard's duplicate-submission guard track when this drop
          // finishes and re-enable dragging that one card.
          onCardDrop={(lead, status) => handleStatusChange(lead, status as LeadStatus)}
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
              onClick={() => void handleSave(duplicateWarning)}
              disabled={pending || !form.first_name.trim() || !form.last_name.trim()}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {duplicateWarning ? 'Save anyway' : pending ? 'Saving…' : 'Save'}
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
          <FormField label="Industry">
            <FormInput
              value={form.industry ?? ''}
              onChange={(event) => setForm({ ...form, industry: event.target.value })}
            />
          </FormField>
          <FormField label="Website">
            <FormInput
              value={form.website ?? ''}
              onChange={(event) => setForm({ ...form, website: event.target.value })}
              placeholder="https://"
            />
          </FormField>
          <FormField label="Company size">
            <FormInput
              value={form.company_size ?? ''}
              onChange={(event) => setForm({ ...form, company_size: event.target.value })}
              placeholder="e.g. 51–200"
            />
          </FormField>
          <FormField label="Product / service interest">
            <FormInput
              value={form.product_interest ?? ''}
              onChange={(event) =>
                setForm({ ...form, product_interest: event.target.value })
              }
              placeholder="What are they evaluating?"
            />
          </FormField>
          <FormField label="Expected deal size">
            <FormInput
              type="number"
              min="0"
              step="0.01"
              value={form.expected_deal_size ?? ''}
              onChange={(event) =>
                setForm({ ...form, expected_deal_size: event.target.value })
              }
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
          <FormField label="Lead owner">
            <FormSelect
              value={form.owner_id ?? ''}
              onChange={(event) => setForm({ ...form, owner_id: event.target.value })}
              placeholder="Unassigned"
              disabled={!mayViewMembers}
              options={members.map((member) => ({
                value: member.user_id,
                label: member.full_name?.trim() || member.email,
              }))}
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
          {!editing && mayViewCampaigns && (
            <FormField
              label="Campaign"
              hint="Attribution can only be set when the lead is created."
            >
              <FormSelect
                value={form.campaign_id ?? ''}
                onChange={(event) => setForm({ ...form, campaign_id: event.target.value })}
                placeholder="No campaign"
                options={campaigns.map((campaign) => ({
                  value: campaign.id,
                  label: campaign.name,
                }))}
              />
            </FormField>
          )}
          <FormField label="Notes">
            <FormTextarea
              value={form.notes ?? ''}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              rows={3}
            />
          </FormField>
          <FormError message={saveError} />
          <CustomFieldInputs
            entityType="LEAD"
            values={customValues}
            onChange={setCustomValues}
            recordContext={{ ...editing, ...form }}
          />
        </div>
      </SlideDrawer>
      {mergeOpen && mergeCandidates(items, selectedIds).length > 1 && (
        <MergeDialog
          open={mergeOpen}
          onClose={() => setMergeOpen(false)}
          entity="leads"
          // The first selected row survives. Which one that is matters, so the
          // dialog names it and the conflict list lets every field be taken
          // from any of the others.
          primary={mergeCandidates(items, selectedIds)[0]}
          duplicates={mergeCandidates(items, selectedIds).slice(1)}
          onMerged={() => {
            setSelectedIds(new Set());
            reload();
          }}
        />
      )}
      {bulkStatusOpen && (
        <BulkStatusDrawer
          count={selectedIds.size}
          onClose={() => setBulkStatusOpen(false)}
          onSubmit={async (targetStatus, lostReason) => {
            const result = await bulkChangeLeadStatus(Array.from(selectedIds), targetStatus, lostReason);
            if (result.failed.length === 0) {
              notifySuccess(`${result.succeeded.length} lead(s) moved to ${humanize(targetStatus)}.`);
            } else if (result.succeeded.length === 0) {
              notifyError(
                new Error(result.failed[0]?.reason ?? 'Failed'),
                'No leads could be moved — see the reasons on each.',
              );
            } else {
              notifySuccess(
                `${result.succeeded.length} lead(s) moved to ${humanize(targetStatus)}.`,
                `${result.failed.length} could not move: ${result.failed
                  .slice(0, 3)
                  .map((f) => f.reason)
                  .join('; ')}`,
              );
            }
            setBulkStatusOpen(false);
            setSelectedIds(new Set());
            reload();
          }}
        />
      )}
    </div>
  );
}

function BulkStatusDrawer({
  count,
  onClose,
  onSubmit,
}: {
  count: number;
  onClose: () => void;
  onSubmit: (status: LeadStatus, lostReason?: string) => Promise<void>;
}) {
  const [targetStatus, setTargetStatus] = useState<LeadStatus>('CONTACTED');
  const [lostReason, setLostReason] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsReason = targetStatus === 'LOST' || targetStatus === 'UNQUALIFIED';

  async function handleSubmit() {
    setPending(true);
    setError(null);
    try {
      await onSubmit(targetStatus, needsReason ? lostReason : undefined);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The bulk move could not be started.');
      setPending(false);
    }
  }

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title={`Move ${count} leads`}
      footer={
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost px-4 py-2 text-[13px]">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={pending}
            className="btn-primary px-4 py-2 text-[13px] disabled:opacity-60"
          >
            {pending ? 'Moving…' : `Move ${count} leads`}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <FormError message={error} />
        <p className="txt-faint text-[12.5px]">
          Each lead moves through the same status rules as a single drag on the board — a lead an
          illegal move or a blueprint refuses is reported, not silently skipped.
        </p>
        <FormField label="New status">
          <FormSelect
            options={LEAD_STATUSES.filter((s) => s !== 'CONVERTED').map((s) => ({
              value: s,
              label: humanize(s),
            }))}
            value={targetStatus}
            onChange={(e) => setTargetStatus(e.target.value as LeadStatus)}
          />
        </FormField>
        {needsReason && (
          <FormField label="Reason" required>
            <FormInput value={lostReason} onChange={(e) => setLostReason(e.target.value)} />
          </FormField>
        )}
      </div>
    </SlideDrawer>
  );
}

/**
 * The selected rows, as the merge dialog wants them.
 *
 * Ordered by the table's own order rather than by click order, so "the first
 * one survives" means the topmost row on screen — which is what a person
 * reading the list expects, and is stable if they click around.
 */
function mergeCandidates(
  rows: Lead[],
  selected: Set<string>,
): { id: string; label: string }[] {
  return rows
    .filter((row) => selected.has(row.id))
    .map((row) => ({ id: row.id, label: `${row.first_name} ${row.last_name}` }));
}
