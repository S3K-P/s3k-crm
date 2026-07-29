'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Users, Plus, Download, Upload,
  MoreHorizontal, Pencil, Trash2
} from 'lucide-react';
import DataTable, { type ColumnDef, type SortDirection } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { cn } from '@/lib/utils';

/* ============================================================
   TYPES
   ============================================================ */

export type ContactStatus = 'Active' | 'Inactive';

interface Contact {
  id: string;
  firstName: string;
  lastName: string;
  jobTitle: string;
  department: string;
  account: string; // Company
  email: string;
  phone: string;
  mobile: string;
  owner: string;
  reportingManager: string;
  status: ContactStatus;
  aiScore: number;
  lastInteraction: string;
  preferredCommunication: string;
  linkedInUrl: string;
  country: string;
  state: string;
  city: string;
  postalCode: string;
  address: string;
  notes: string;
}

type DrawerMode = 'add' | 'edit';

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: Contact[] = [
  { id: '1', firstName: 'Sarah', lastName: 'Chen', jobTitle: 'Chief Marketing Officer', department: 'Marketing', account: 'Acme Corp', email: 'sarah.c@acme.com', phone: '+1 555-0101', mobile: '+1 555-0102', owner: 'Mike Johnson', reportingManager: '', status: 'Active', aiScore: 95, lastInteraction: '2 hours ago', preferredCommunication: 'Email', linkedInUrl: 'linkedin.com/in/sarahchen', country: 'USA', state: 'CA', city: 'San Francisco', postalCode: '94105', address: '123 Tech Blvd', notes: 'Key decision maker for marketing suite.' },
  { id: '2', firstName: 'James', lastName: 'Rodriguez', jobTitle: 'VP of Procurement', department: 'Operations', account: 'Globex Ltd', email: 'jrodriguez@globex.com', phone: '+44 20 7123 4567', mobile: '+44 7700 900000', owner: 'Priya Patel', reportingManager: '', status: 'Active', aiScore: 78, lastInteraction: '1 day ago', preferredCommunication: 'Phone', linkedInUrl: 'linkedin.com/in/jrodriguez', country: 'UK', state: 'London', city: 'London', postalCode: 'EC1A 1BB', address: '45 Industrial Way', notes: 'Prefers calls over emails.' },
  { id: '3', firstName: 'Alice', lastName: 'Johnson', jobTitle: 'IT Director', department: 'IT', account: 'Initech', email: 'alice.j@initech.com', phone: '+1 555-0103', mobile: '', owner: 'Sarah Chen', reportingManager: '', status: 'Active', aiScore: 82, lastInteraction: '3 days ago', preferredCommunication: 'Email', linkedInUrl: 'linkedin.com/in/alicej', country: 'USA', state: 'TX', city: 'Austin', postalCode: '78701', address: '789 Startup Ln', notes: 'Evaluating our security compliance.' },
  { id: '4', firstName: 'Bob', lastName: 'Williams', jobTitle: 'Chief Security Officer', department: 'Security', account: 'Stark Ind', email: 'bwilliams@stark.com', phone: '+1 555-0104', mobile: '+1 555-0105', owner: 'Mike Johnson', reportingManager: 'Tony Stark', status: 'Active', aiScore: 98, lastInteraction: 'Just now', preferredCommunication: 'Meeting', linkedInUrl: '', country: 'USA', state: 'NY', city: 'New York', postalCode: '10001', address: 'Avengers Tower', notes: 'Requires weekly syncs.' },
  { id: '5', firstName: 'Charlie', lastName: 'Brown', jobTitle: 'Finance Manager', department: 'Finance', account: 'Wayne Ent', email: 'cbrown@wayne.com', phone: '+1 555-0106', mobile: '', owner: 'James Rodriguez', reportingManager: 'Lucius Fox', status: 'Inactive', aiScore: 40, lastInteraction: '2 months ago', preferredCommunication: 'Email', linkedInUrl: '', country: 'USA', state: 'NJ', city: 'Gotham', postalCode: '07001', address: '1007 Mountain Drive', notes: 'Left company.' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'Active', label: 'Active' },
  { value: 'Inactive', label: 'Inactive' },
];

const ACCOUNT_OPTIONS = [
  { value: '', label: 'All Accounts' },
  { value: 'Acme Corp', label: 'Acme Corp' },
  { value: 'Globex Ltd', label: 'Globex Ltd' },
  { value: 'Initech', label: 'Initech' },
  { value: 'Stark Ind', label: 'Stark Ind' },
  { value: 'Wayne Ent', label: 'Wayne Ent' },
];

const EMPTY_FORM: Partial<Contact> = {
  firstName: '', lastName: '', jobTitle: '', department: '', account: '', email: '', phone: '', mobile: '',
  owner: '', reportingManager: '', status: 'Active', preferredCommunication: 'Email', linkedInUrl: '',
  country: '', state: '', city: '', postalCode: '', address: '', notes: ''
};

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function ContactsPage() {
  const router = useRouter();

  /* ---- State ---- */
  const [data, setData] = useState<Contact[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [accountFilter, setAccountFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('add');
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<Contact>>(EMPTY_FORM);
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.firstName.toLowerCase().includes(q) ||
        r.lastName.toLowerCase().includes(q) ||
        r.email.toLowerCase().includes(q) ||
        r.jobTitle.toLowerCase().includes(q)
      );
    }
    if (statusFilter) rows = rows.filter(r => r.status === statusFilter);
    if (accountFilter) rows = rows.filter(r => r.account === accountFilter);
    
    if (sortKey && sortDir) {
      rows = [...rows].sort((a, b) => {
        const aVal = (a as unknown as Record<string, unknown>)[sortKey];
        const bVal = (b as unknown as Record<string, unknown>)[sortKey];
        if (typeof aVal === 'number' && typeof bVal === 'number') {
          return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
        }
        const aStr = String(aVal ?? '').toLowerCase();
        const bStr = String(bVal ?? '').toLowerCase();
        return sortDir === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
      });
    }
    return rows;
  }, [data, search, statusFilter, accountFilter, sortKey, sortDir]);

  /* ---- Sort handler ---- */
  const handleSort = useCallback((key: string) => {
    setSortKey(prev => {
      if (prev === key) {
        setSortDir(d => (d === 'asc' ? 'desc' : d === 'desc' ? null : 'asc'));
        return key;
      }
      setSortDir('asc');
      return key;
    });
  }, []);

  /* ---- Handlers ---- */
  const handleRowClick = (row: Contact) => router.push(`/contacts/${row.id}`);

  const openAdd = () => {
    setDrawerMode('add');
    setEditId(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  };

  const openEdit = (row: Contact) => {
    setDrawerMode('edit');
    setEditId(row.id);
    setForm({ ...row });
    setDrawerOpen(true);
    setOpenActionId(null);
  };

  const handleSave = () => {
    if (!form.firstName?.trim() || !form.lastName?.trim() || !form.email?.trim()) return;

    if (drawerMode === 'add') {
      const newItem: Contact = {
        ...(form as Contact),
        id: String(Date.now()),
        aiScore: Math.floor(Math.random() * 100),
        lastInteraction: 'Just now',
      };
      setData(prev => [newItem, ...prev]);
    } else if (editId) {
      setData(prev => prev.map(r => r.id === editId ? { ...r, ...(form as Contact) } : r));
    }

    setDrawerOpen(false);
  };

  const handleDelete = (id: string) => {
    setData(prev => prev.filter(r => r.id !== id));
    setOpenActionId(null);
  };

  /* ---- Table Columns ---- */
  const columns: ColumnDef<Contact>[] = [
    {
      key: 'name', label: 'Full Name', sortable: true, minWidth: '180px',
      render: (row) => <span className="txt text-[13px] font-semibold">{row.firstName} {row.lastName}</span>,
    },
    { key: 'jobTitle', label: 'Job Title', sortable: true, hideBelow: 'md', render: (row) => <span className="txt-muted text-[12.5px]">{row.jobTitle}</span> },
    { key: 'account', label: 'Account', sortable: true, hideBelow: 'sm', render: (row) => <span className="txt-muted text-[12.5px]">{row.account}</span> },
    { key: 'email', label: 'Email', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px]">{row.email}</span> },
    { key: 'phone', label: 'Phone', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px]">{row.phone}</span> },
    { key: 'owner', label: 'Contact Owner', hideBelow: 'xl', render: (row) => <span className="txt-muted text-[12.5px] font-medium">{row.owner}</span> },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge label={row.status} variant={row.status === 'Active' ? 'success' : 'neutral'} /> },
    { key: 'lastInteraction', label: 'Last Interaction', hideBelow: 'xl', render: (row) => <span className="txt-faint text-[12px]">{row.lastInteraction}</span> },
    {
      key: 'aiScore', label: 'Relationship', sortable: true, align: 'center',
      render: (row) => (
        <span className={cn("font-display text-[14px] font-bold", row.aiScore >= 80 ? 'text-emerald-500' : row.aiScore >= 60 ? 'text-amber-500' : 'text-rose-500')}>
          {row.aiScore}
        </span>
      ),
    },
    {
      key: 'actions', label: '', align: 'right',
      render: (row) => (
        <div className="relative">
          <button
            className="ctl grid h-7 w-7 place-items-center rounded-lg transition hover:opacity-80"
            onClick={(e) => { e.stopPropagation(); setOpenActionId(prev => prev === row.id ? null : row.id); }}
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
          {openActionId === row.id && (
            <>
              <div className="fixed inset-0 z-10" onClick={(e) => { e.stopPropagation(); setOpenActionId(null); }} />
              <div className="surface bd absolute right-0 top-full z-20 mt-1 w-36 overflow-hidden rounded-xl border shadow-lg">
                <button
                  className="flex w-full items-center gap-2 px-3 py-2 text-[12.5px] font-medium transition-colors hover:surface-2"
                  onClick={(e) => { e.stopPropagation(); openEdit(row); }}
                >
                  <Pencil className="h-3.5 w-3.5" style={{ color: 'var(--accent)' }} />
                  <span className="txt">Edit</span>
                </button>
                <button
                  className="flex w-full items-center gap-2 px-3 py-2 text-[12.5px] font-medium text-red-500 transition-colors hover:surface-2"
                  onClick={(e) => { e.stopPropagation(); handleDelete(row.id); }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              </div>
            </>
          )}
        </div>
      ),
    },
  ];

  /* ---- Render ---- */
  return (
    <>
      <div className="flex h-full flex-col space-y-5 p-6 lg:p-8">
        {/* ── Page Header ── */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-emerald-500 to-green-600">
              <Users className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight txt">Contacts</h1>
              <p className="txt-muted mt-0.5 text-[13px] font-medium">Manage people associated with accounts</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Upload className="h-4 w-4" /> Import
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Download className="h-4 w-4" /> Export
            </button>
            <button
              onClick={openAdd}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              <Plus className="h-4 w-4" /> Add Contact
            </button>
          </div>
        </div>

        {/* ── Filters Bar ── */}
        <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
          <SearchInput placeholder="Search contacts..." value={search} onChange={(e) => setSearch(e.target.value)} containerClassName="flex-1 sm:max-w-xs" />
          <div className="flex flex-wrap gap-2">
            <FilterSelect options={ACCOUNT_OPTIONS} value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)} />
            <FilterSelect options={STATUS_OPTIONS} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
          </div>
        </div>

        {/* ── Data Table ── */}
        <div className="min-h-[400px] flex-1">
          <div className="surface bd overflow-hidden rounded-2xl border">
            <DataTable<Contact>
              columns={columns}
              data={filtered}
              rowKey={(row) => row.id}
              sortKey={sortKey}
              sortDirection={sortDir}
              onSort={handleSort}
              onRowClick={handleRowClick}
              emptyMessage="No contacts found"
            />
          </div>
        </div>
      </div>

      {/* ── Add / Edit Drawer ── */}
      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={drawerMode === 'add' ? 'Add Contact' : 'Edit Contact'}
        subtitle={drawerMode === 'add' ? 'Create a new contact record' : 'Update contact details'}
        width="max-w-2xl"
        footer={
          <>
            <button onClick={() => setDrawerOpen(false)} className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80">Cancel</button>
            <button onClick={handleSave} className="rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
              {drawerMode === 'add' ? 'Save' : 'Update'}
            </button>
          </>
        }
      >
        <div className="space-y-6">
          {/* Personal Info */}
          <div>
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Personal Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="First Name" required><FormInput value={form.firstName} onChange={(e) => setForm({ ...form, firstName: e.target.value })} /></FormField>
              <FormField label="Last Name" required><FormInput value={form.lastName} onChange={(e) => setForm({ ...form, lastName: e.target.value })} /></FormField>
              <FormField label="Job Title"><FormInput value={form.jobTitle} onChange={(e) => setForm({ ...form, jobTitle: e.target.value })} /></FormField>
              <FormField label="Department"><FormInput value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></FormField>
              <FormField label="Email" required><FormInput type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></FormField>
              <FormField label="Phone"><FormInput type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></FormField>
              <FormField label="Mobile"><FormInput type="tel" value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></FormField>
            </div>
          </div>
          
          {/* Company Association */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Company Association</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Account"><FormSelect options={ACCOUNT_OPTIONS.filter(o => o.value !== '')} value={form.account} onChange={(e) => setForm({ ...form, account: e.target.value })} /></FormField>
              <FormField label="Reporting Manager"><FormInput value={form.reportingManager} onChange={(e) => setForm({ ...form, reportingManager: e.target.value })} /></FormField>
              <FormField label="Contact Owner"><FormInput value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></FormField>
            </div>
          </div>
          
          {/* Address */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Address</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Country"><FormInput value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} /></FormField>
              <FormField label="State/Province"><FormInput value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} /></FormField>
              <FormField label="City"><FormInput value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></FormField>
              <FormField label="Postal Code"><FormInput value={form.postalCode} onChange={(e) => setForm({ ...form, postalCode: e.target.value })} /></FormField>
            </div>
            <div className="mt-4">
              <FormField label="Street Address"><FormTextarea value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></FormField>
            </div>
          </div>

          {/* CRM Info */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">CRM Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Status"><FormSelect options={STATUS_OPTIONS.filter(o => o.value !== '')} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as ContactStatus })} /></FormField>
              <FormField label="Preferred Comm."><FormSelect options={[{ value: 'Email', label: 'Email' }, { value: 'Phone', label: 'Phone' }, { value: 'Meeting', label: 'Meeting' }]} value={form.preferredCommunication} onChange={(e) => setForm({ ...form, preferredCommunication: e.target.value })} /></FormField>
              <FormField label="LinkedIn URL"><FormInput value={form.linkedInUrl} onChange={(e) => setForm({ ...form, linkedInUrl: e.target.value })} /></FormField>
            </div>
            <div className="mt-4">
               <FormField label="Notes"><FormTextarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></FormField>
            </div>
          </div>
        </div>
      </SlideDrawer>
    </>
  );
}
