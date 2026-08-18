'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Contact as ContactIcon, Plus, Pencil, Trash2, Loader2 } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import { listAccounts, type Account } from '@/features/crm/accounts';
import {
  CONTACT_STATUSES,
  archiveContact,
  createContact,
  listContacts,
  updateContact,
  type Contact,
  type ContactInput,
  type ContactStatus,
} from '@/features/crm/contacts';

/* ============================================================
   CONTACTS

   Rows come from `GET /api/v1/crm/contacts`. The account field
   is a real picker backed by `GET /crm/accounts`, writing an
   `account_id` foreign key — the string-matching anti-pattern
   W12 exists to remove.
   ============================================================ */

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...CONTACT_STATUSES.map((value) => ({ value, label: humanize(value) })),
];

const EMPTY_FORM: ContactInput = {
  first_name: '',
  last_name: '',
  account_id: '',
  email: '',
  phone: '',
  job_title: '',
  status: 'ACTIVE',
};

export default function ContactsPage() {
  const router = useRouter();
  const { can } = usePermissions();
  const mayCreate = can('contacts', 'CREATE');
  const mayEdit = can('contacts', 'EDIT');
  const mayDelete = can('contacts', 'DELETE');
  const mayViewAccounts = can('accounts', 'VIEW');

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () =>
      listContacts({
        page,
        page_size: 25,
        search: search.trim() || null,
        status: (statusFilter || null) as ContactStatus | null,
        sort_by: 'last_name',
        sort_dir: 'asc',
      }),
    [page, search, statusFilter],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Contact>(
    fetcher,
    [page, search, statusFilter],
    { errorMessage: 'Something went wrong loading contacts.' },
  );

  /* ---- Account options for the picker -------------------------------------
     Loaded once and kept in a map so the table can show an account name
     instead of a UUID without a request per row. A rep who cannot view
     accounts simply gets no picker rather than a failed request. */
  const [accounts, setAccounts] = useState<Account[]>([]);
  useEffect(() => {
    if (!mayViewAccounts) return;
    let cancelled = false;
    void (async () => {
      try {
        const page = await listAccounts({ page_size: 200, sort_by: 'name', sort_dir: 'asc' });
        if (!cancelled) setAccounts(page.data);
      } catch {
        // Non-fatal: the contact list still works, the picker is just empty.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewAccounts]);

  const accountNames = useMemo(
    () => new Map(accounts.map((account) => [account.id, account.name])),
    [accounts],
  );

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Contact | null>(null);
  const [form, setForm] = useState<ContactInput>(EMPTY_FORM);
  const [duplicateWarning, setDuplicateWarning] = useState(false);
  const { pending, error: saveError, clearError, run } = useMutation();

  const openAdd = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDuplicateWarning(false);
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: Contact) => {
    setEditing(row);
    setForm({
      first_name: row.first_name,
      last_name: row.last_name,
      account_id: row.account_id ?? '',
      email: row.email ?? '',
      phone: row.phone ?? '',
      job_title: row.job_title ?? '',
      status: row.status,
    });
    setDuplicateWarning(false);
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async (allowDuplicate = false) => {
    if (!form.first_name.trim() || !form.last_name.trim()) return;
    const body: ContactInput = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      account_id: form.account_id || null,
      email: form.email?.trim() || null,
      phone: form.phone?.trim() || null,
      job_title: form.job_title?.trim() || null,
      status: form.status,
    };

    const saved = await run(() =>
      editing
        ? updateContact(editing.id, body, allowDuplicate)
        : createContact(body, allowDuplicate),
    );

    if (saved === undefined) {
      if (!allowDuplicate) setDuplicateWarning(true);
      return;
    }
    setDrawerOpen(false);
    setDuplicateWarning(false);
    reload();
  };

  const handleDelete = async (row: Contact) => {
    const done = await run(() => archiveContact(row.id));
    if (done !== undefined) reload();
  };

  const columns = useMemo<ColumnDef<Contact>[]>(
    () => [
      { key: 'full_name', label: 'Name', minWidth: '180px' },
      {
        key: 'account_id',
        label: 'Account',
        hideBelow: 'md',
        render: (row) =>
          row.account_id ? (
            accountNames.get(row.account_id) ?? <span className="txt-faint">—</span>
          ) : (
            <span className="txt-faint">—</span>
          ),
      },
      {
        key: 'email',
        label: 'Email',
        hideBelow: 'lg',
        render: (row) => row.email ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'job_title',
        label: 'Title',
        hideBelow: 'xl',
        render: (row) => row.job_title ?? <span className="txt-faint">—</span>,
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
                aria-label={`Edit ${row.full_name}`}
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
                aria-label={`Archive ${row.full_name}`}
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
    [mayEdit, mayDelete, accountNames],
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-600">
            <ContactIcon className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Contacts</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              The people you work with, linked to their accounts.
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
            <Plus className="h-4 w-4" /> New contact
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
          placeholder="Search name, email or title…"
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

      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : (
        <DataTable
          columns={columns}
          data={items}
          rowKey={(row) => row.id}
          onRowClick={(row) => router.push(`/contacts/${row.id}`)}
          loading={status === 'loading'}
          skeletonRows={6}
          emptyState={
            <ListEmpty
              title="No contacts yet"
              hint={
                search || statusFilter
                  ? 'No contact matches those filters.'
                  : 'Add people directly, or convert a lead to create an account and its first contact together.'
              }
            />
          }
        />
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit contact' : 'New contact'}
        subtitle={editing ? editing.full_name : 'Add a person to your CRM.'}
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
          <FormField
            label="Account"
            hint={
              mayViewAccounts
                ? 'Links this person to a company record.'
                : 'You do not have permission to browse accounts.'
            }
          >
            <FormSelect
              value={form.account_id ?? ''}
              onChange={(event) => setForm({ ...form, account_id: event.target.value })}
              placeholder="No account"
              disabled={!mayViewAccounts}
              options={accounts.map((account) => ({
                value: account.id,
                label: account.name,
              }))}
            />
          </FormField>
          <FormField label="Email">
            <FormInput
              type="email"
              value={form.email ?? ''}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
              placeholder="person@company.com"
            />
          </FormField>
          <FormField label="Phone">
            <FormInput
              value={form.phone ?? ''}
              onChange={(event) => setForm({ ...form, phone: event.target.value })}
            />
          </FormField>
          <FormField label="Job title">
            <FormInput
              value={form.job_title ?? ''}
              onChange={(event) => setForm({ ...form, job_title: event.target.value })}
            />
          </FormField>
          <FormField label="Status">
            <FormSelect
              value={form.status ?? 'ACTIVE'}
              onChange={(event) =>
                setForm({ ...form, status: event.target.value as ContactStatus })
              }
              options={CONTACT_STATUSES.map((value) => ({ value, label: humanize(value) }))}
            />
          </FormField>
          <FormError message={saveError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
