'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Building2, GitMerge, Loader2, Pencil, Plus, Trash2, Upload } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess, notifyWarning } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import MergeDialog from '@/components/crm/dialogs/MergeDialog';
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
import {
  ACCOUNT_STATUSES,
  archiveAccount,
  createAccount,
  exportAccounts,
  listAccounts,
  updateAccount,
  type Account,
  type AccountInput,
  type AccountStatus,
} from '@/features/crm/accounts';

/* ============================================================
   ACCOUNTS

   Rows come from `GET /api/v1/crm/accounts`, organization-scoped
   by the backend. Create, edit and archive all round-trip, so
   the table reflects the database rather than component state.

   The backend refuses to archive an account that still has open
   opportunities and returns 409; that message is surfaced as-is
   rather than being second-guessed here.
   ============================================================ */

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...ACCOUNT_STATUSES.map((value) => ({ value, label: humanize(value) })),
];

const STATUS_FORM_OPTIONS = ACCOUNT_STATUSES.map((value) => ({
  value,
  label: humanize(value),
}));

const EMPTY_FORM: AccountInput = {
  name: '',
  industry: '',
  website: '',
  phone: '',
  company_size: '',
  status: 'ACTIVE',
  city: '',
  country: '',
  description: '',
};

export default function AccountsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('accounts', 'CREATE');
  const mayExport = can('accounts', 'EXPORT');
  const [importOpen, setImportOpen] = useState(false);
  const mayEdit = can('accounts', 'EDIT');
  const mayDelete = can('accounts', 'DELETE');
  // Merging is an edit *and* a deletion, so the control is offered only to
  // somebody holding both — the same pair the endpoint demands. Hiding it
  // protects nothing on its own; it stops offering a button that would 403.
  const mayMerge = mayEdit && mayDelete;
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [mergeOpen, setMergeOpen] = useState(false);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () =>
      listAccounts({
        page,
        page_size: 25,
        search: search.trim() || null,
        status: (statusFilter || null) as AccountStatus | null,
        sort_by: 'name',
        sort_dir: 'asc',
      }),
    [page, search, statusFilter],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Account>(
    fetcher,
    [page, search, statusFilter],
    { errorMessage: 'Something went wrong loading accounts.' },
  );

  const [drawerOpen, setDrawerOpen] = useState(false);
  // Custom values are held apart from `form` because they are keyed by tenant
  // data: folding them into a typed `AccountInput` would mean giving that
  // interface an index signature, and losing every check on the real columns.
  const [customValues, setCustomValues] = useState<CustomFieldValues>({});
  const [editing, setEditing] = useState<Account | null>(null);
  const [form, setForm] = useState<AccountInput>(EMPTY_FORM);
  const [duplicateWarning, setDuplicateWarning] = useState(false);
  const { pending, error: saveError, clearError, run } = useMutation();

  const openAdd = () => {
    setCustomValues({});
    setEditing(null);
    setForm(EMPTY_FORM);
    setDuplicateWarning(false);
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: Account) => {
    setCustomValues(row.custom_fields ?? {});
    setEditing(row);
    setForm({
      name: row.name,
      industry: row.industry ?? '',
      website: row.website ?? '',
      phone: row.phone ?? '',
      company_size: row.company_size ?? '',
      status: row.status,
      city: row.city ?? '',
      country: row.country ?? '',
      description: row.description ?? '',
    });
    setDuplicateWarning(false);
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async (allowDuplicate = false) => {
    if (!form.name.trim()) return;
    const body: AccountInput = {
      name: form.name.trim(),
      industry: form.industry?.trim() || null,
      website: form.website?.trim() || null,
      phone: form.phone?.trim() || null,
      company_size: form.company_size?.trim() || null,
      status: form.status,
      city: form.city?.trim() || null,
      country: form.country?.trim() || null,
      description: form.description?.trim() || null,
      // Only what the user actually touched. Sending the whole document would
      // be harmless but noisy; sending `{}` when they touched nothing would
      // *clear* every custom value on the record.
      ...(Object.keys(changedValues(customValues, editing?.custom_fields)).length > 0
        ? { custom_fields: changedValues(customValues, editing?.custom_fields) }
        : {}),
    };

    const saved = await run(() =>
      editing ? updateAccount(editing.id, body) : createAccount(body, allowDuplicate),
    );

    if (saved === undefined) {
      // A duplicate name is a warning, not a rejection (decision C03): offer
      // the override rather than making the user rename a real second office.
      if (!editing && !allowDuplicate) {
        setDuplicateWarning(true);
        notifyWarning(
          'An account with that name already exists',
          'Press "Save anyway" to create a second record — a separate office or subsidiary, say.',
        );
      }
      return;
    }
    setDrawerOpen(false);
    setDuplicateWarning(false);
    notifySuccess(editing ? 'Account updated' : 'Account created', body.name);
    reload();
  };

  const handleDelete = async (row: Account) => {
    const ok = await confirm({
      title: `Archive ${row.name}?`,
      description:
        'Its contacts, opportunities and activities stay in the database and keep pointing at it. The backend refuses the archive outright while the account still has open opportunities.',
      confirmLabel: 'Archive account',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveAccount(row.id);
      notifySuccess('Account archived', row.name);
      reload();
    } catch (caught) {
      // Typically "this account still has open opportunities" — the reason
      // the server gave, not a generic failure.
      notifyError(caught, 'The account could not be archived.');
    }
  };

  const columns = useMemo<ColumnDef<Account>[]>(
    () => [
      ...(mayMerge
        ? [
            {
              key: 'select',
              label: '',
              minWidth: '36px',
              render: (row: Account) => (
                <input
                  type="checkbox"
                  aria-label={`Select ${row.name}`}
                  checked={selectedIds.has(row.id)}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => {
                    // A new Set each time: mutating the held one would not
                    // change its identity and React would not re-render.
                    const next = new Set(selectedIds);
                    if (event.target.checked) next.add(row.id);
                    else next.delete(row.id);
                    setSelectedIds(next);
                  }}
                  className="h-3.5 w-3.5"
                />
              ),
            } satisfies ColumnDef<Account>,
          ]
        : []),
      { key: 'name', label: 'Account', minWidth: '200px' },
      {
        key: 'industry',
        label: 'Industry',
        hideBelow: 'md',
        render: (row) => row.industry ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'city',
        label: 'Location',
        hideBelow: 'lg',
        render: (row) =>
          [row.city, row.country].filter(Boolean).join(', ') || (
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mayEdit, mayDelete, mayMerge, selectedIds],
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-amber-500 to-orange-500">
            <Building2 className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Accounts</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              The companies you do business with.
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
            <Plus className="h-4 w-4" /> New account
          </button>
        )}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SavedViewPicker
          entityType="ACCOUNT"
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
        />
        <SearchInput
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder="Search accounts…"
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
            entityPlural="accounts"
            count={pagination?.total}
            onExport={() =>
              exportAccounts({
                search: search.trim() || null,
                status: (statusFilter || null) as AccountStatus | null,
              })
            }
          />
        )}
        <div className="ml-auto">
          <ResultCount shown={items.length} total={pagination?.total ?? 0} />
        </div>
      </div>

      <ImportWizard
        open={importOpen}
        onClose={() => setImportOpen(false)}
        slug="accounts"
        onImported={reload}
      />

      {mayMerge && mergeCandidates(items, selectedIds).length > 1 && (
        <div className="ctl mb-3 flex flex-wrap items-center gap-3 rounded-lg px-4 py-2.5">
          <span className="txt text-[13px] font-semibold">
            {mergeCandidates(items, selectedIds).length} selected
          </span>
          <button
            type="button"
            onClick={() => setMergeOpen(true)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <GitMerge className="h-3.5 w-3.5" /> Merge duplicates
          </button>
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="txt-faint text-[12px] underline transition hover:opacity-70"
          >
            Clear selection
          </button>
        </div>
      )}
      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : (
        <DataTable
          columns={columns}
          data={items}
          rowKey={(row) => row.id}
          onRowClick={(row) => router.push(`/accounts/${row.id}`)}
          loading={status === 'loading'}
          skeletonRows={6}
          emptyState={
            <ListEmpty
              title="No accounts yet"
              hint={
                search || statusFilter
                  ? 'No account matches those filters.'
                  : 'Accounts you create — or that come from converting a lead — appear here.'
              }
            />
          }
        />
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit account' : 'New account'}
        subtitle={editing ? editing.name : 'Add a company to your CRM.'}
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
              disabled={pending || !form.name.trim()}
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
          <FormField label="Name" required>
            <FormInput
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Acme Corp"
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
              placeholder="acme.com"
            />
          </FormField>
          <FormField label="Phone">
            <FormInput
              type="tel"
              value={form.phone ?? ''}
              onChange={(event) => setForm({ ...form, phone: event.target.value })}
              placeholder="+1 555 123 4567"
            />
          </FormField>
          <FormField label="Company size">
            <FormInput
              value={form.company_size ?? ''}
              onChange={(event) => setForm({ ...form, company_size: event.target.value })}
              placeholder="100-500"
            />
          </FormField>
          <FormField label="Status">
            <FormSelect
              value={form.status ?? 'ACTIVE'}
              onChange={(event) =>
                setForm({ ...form, status: event.target.value as AccountStatus })
              }
              options={STATUS_FORM_OPTIONS}
            />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="City">
              <FormInput
                value={form.city ?? ''}
                onChange={(event) => setForm({ ...form, city: event.target.value })}
              />
            </FormField>
            <FormField label="Country">
              <FormInput
                value={form.country ?? ''}
                onChange={(event) => setForm({ ...form, country: event.target.value })}
              />
            </FormField>
          </div>
          <FormField label="Description">
            <FormTextarea
              value={form.description ?? ''}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              rows={3}
            />
          </FormField>
          <FormError message={saveError} />
          <CustomFieldInputs
            entityType="ACCOUNT"
            values={customValues}
            onChange={setCustomValues}
          />
        </div>
      </SlideDrawer>
      {mergeOpen && mergeCandidates(items, selectedIds).length > 1 && (
        <MergeDialog
          open={mergeOpen}
          onClose={() => setMergeOpen(false)}
          entity="accounts"
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
    </div>
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
  rows: Account[],
  selected: Set<string>,
): { id: string; label: string }[] {
  return rows
    .filter((row) => selected.has(row.id))
    .map((row) => ({ id: row.id, label: row.name }));
}
