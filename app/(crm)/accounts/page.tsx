'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Building2, Plus, Download, Upload,
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

export type AccountStatus = 'Active' | 'Churned' | 'Onboarding' | 'At Risk';

interface Account {
  id: string;
  name: string;
  industry: string;
  website: string;
  primaryContact: string;
  owner: string;
  openOpportunities: number;
  totalPipelineValue: string;
  healthScore: number;
  lastActivity: string;
  status: AccountStatus;
  companySize: string;
  annualRevenue: string;
  country: string;
  state: string;
  city: string;
  postalCode: string;
  address: string;
  source: string;
  description: string;
}

type DrawerMode = 'add' | 'edit';

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: Account[] = [
  { id: '1', name: 'Acme Corp', industry: 'Technology', website: 'acme.com', primaryContact: 'Sarah Chen', owner: 'Mike Johnson', openOpportunities: 2, totalPipelineValue: '$150,000', healthScore: 92, lastActivity: '2 hours ago', status: 'Active', companySize: '100-500', annualRevenue: '$50M+', country: 'USA', state: 'CA', city: 'San Francisco', postalCode: '94105', address: '123 Tech Blvd', source: 'Direct', description: 'Key enterprise account.' },
  { id: '2', name: 'Globex Ltd', industry: 'Manufacturing', website: 'globex.com', primaryContact: 'James Rodriguez', owner: 'Priya Patel', openOpportunities: 1, totalPipelineValue: '$75,000', healthScore: 68, lastActivity: '1 day ago', status: 'At Risk', companySize: '500+', annualRevenue: '$250M+', country: 'UK', state: 'London', city: 'London', postalCode: 'EC1A 1BB', address: '45 Industrial Way', source: 'Partner', description: 'Global manufacturing firm.' },
  { id: '3', name: 'Initech', industry: 'Software', website: 'initech.com', primaryContact: 'Alice Johnson', owner: 'Sarah Chen', openOpportunities: 0, totalPipelineValue: '$0', healthScore: 85, lastActivity: '3 days ago', status: 'Onboarding', companySize: '50-100', annualRevenue: '$10M+', country: 'USA', state: 'TX', city: 'Austin', postalCode: '78701', address: '789 Startup Ln', source: 'Inbound', description: 'Fast-growing software startup.' },
  { id: '4', name: 'Stark Ind', industry: 'Defense', website: 'stark.com', primaryContact: 'Bob Williams', owner: 'Mike Johnson', openOpportunities: 3, totalPipelineValue: '$1,500,000', healthScore: 98, lastActivity: 'Just now', status: 'Active', companySize: '1000+', annualRevenue: '$1B+', country: 'USA', state: 'NY', city: 'New York', postalCode: '10001', address: 'Avengers Tower', source: 'Referral', description: 'Strategic defense contractor.' },
  { id: '5', name: 'Wayne Ent', industry: 'Finance', website: 'wayne.com', primaryContact: 'Charlie Brown', owner: 'James Rodriguez', openOpportunities: 0, totalPipelineValue: '$0', healthScore: 45, lastActivity: '2 weeks ago', status: 'Churned', companySize: '500+', annualRevenue: '$500M+', country: 'USA', state: 'NJ', city: 'Gotham', postalCode: '07001', address: '1007 Mountain Drive', source: 'Direct', description: 'Former enterprise client.' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'Active', label: 'Active' },
  { value: 'Onboarding', label: 'Onboarding' },
  { value: 'At Risk', label: 'At Risk' },
  { value: 'Churned', label: 'Churned' },
];

const INDUSTRY_OPTIONS = [
  { value: '', label: 'All Industries' },
  { value: 'Technology', label: 'Technology' },
  { value: 'Manufacturing', label: 'Manufacturing' },
  { value: 'Software', label: 'Software' },
  { value: 'Defense', label: 'Defense' },
  { value: 'Finance', label: 'Finance' },
];

const EMPTY_FORM: Partial<Account> = {
  name: '', industry: '', website: '', companySize: '', annualRevenue: '',
  country: '', state: '', city: '', postalCode: '', address: '',
  owner: '', status: 'Active', source: '', description: ''
};

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function AccountsPage() {
  const router = useRouter();

  /* ---- State ---- */
  const [data, setData] = useState<Account[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [industryFilter, setIndustryFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('add');
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<Account>>(EMPTY_FORM);
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.name.toLowerCase().includes(q) ||
        r.website.toLowerCase().includes(q) ||
        r.primaryContact.toLowerCase().includes(q)
      );
    }
    if (statusFilter) rows = rows.filter(r => r.status === statusFilter);
    if (industryFilter) rows = rows.filter(r => r.industry === industryFilter);
    
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
  }, [data, search, statusFilter, industryFilter, sortKey, sortDir]);

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
  const handleRowClick = (row: Account) => router.push(`/accounts/${row.id}`);

  const openAdd = () => {
    setDrawerMode('add');
    setEditId(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  };

  const openEdit = (row: Account) => {
    setDrawerMode('edit');
    setEditId(row.id);
    setForm({ ...row });
    setDrawerOpen(true);
    setOpenActionId(null);
  };

  const handleSave = () => {
    if (!form.name?.trim()) return;

    if (drawerMode === 'add') {
      const newItem: Account = {
        ...(form as Account),
        id: String(Date.now()),
        primaryContact: 'Unassigned', // Will be set via contacts
        openOpportunities: 0,
        totalPipelineValue: '$0',
        healthScore: 100, // Initial perfect score
        lastActivity: 'Just now',
      };
      setData(prev => [newItem, ...prev]);
    } else if (editId) {
      setData(prev => prev.map(r => r.id === editId ? { ...r, ...(form as Account) } : r));
    }

    setDrawerOpen(false);
  };

  const handleDelete = (id: string) => {
    setData(prev => prev.filter(r => r.id !== id));
    setOpenActionId(null);
  };

  /* ---- Table Columns ---- */
  const columns: ColumnDef<Account>[] = [
    {
      key: 'name', label: 'Account Name', sortable: true, minWidth: '180px',
      render: (row) => <span className="txt text-[13px] font-semibold">{row.name}</span>,
    },
    { key: 'industry', label: 'Industry', sortable: true, hideBelow: 'md', render: (row) => <span className="txt-muted text-[12.5px]">{row.industry}</span> },
    { key: 'website', label: 'Website', hideBelow: 'lg', render: (row) => <a href={`https://${row.website}`} target="_blank" rel="noopener noreferrer" className="txt-muted hover:text-[var(--accent)] text-[12.5px]">{row.website}</a> },
    { key: 'primaryContact', label: 'Primary Contact', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px]">{row.primaryContact}</span> },
    { key: 'owner', label: 'Account Owner', hideBelow: 'md', render: (row) => <span className="txt-muted text-[12.5px] font-medium">{row.owner}</span> },
    {
      key: 'openOpportunities', label: 'Open Opps', sortable: true, align: 'center', hideBelow: 'xl',
      render: (row) => <span className="txt text-[13px] font-semibold">{row.openOpportunities}</span>,
    },
    {
      key: 'totalPipelineValue', label: 'Pipeline Value', sortable: true, align: 'right', hideBelow: 'xl',
      render: (row) => <span className="txt font-display text-[14px] font-bold">{row.totalPipelineValue}</span>,
    },
    {
      key: 'healthScore', label: 'Health', sortable: true, align: 'center',
      render: (row) => (
        <span className={cn("font-display text-[14px] font-bold", row.healthScore >= 80 ? 'text-emerald-500' : row.healthScore >= 60 ? 'text-amber-500' : 'text-rose-500')}>
          {row.healthScore}
        </span>
      ),
    },
    { key: 'lastActivity', label: 'Last Activity', hideBelow: 'xl', render: (row) => <span className="txt-faint text-[12px]">{row.lastActivity}</span> },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge label={row.status} variant={row.status === 'Active' ? 'success' : row.status === 'Onboarding' ? 'accent' : row.status === 'At Risk' ? 'warning' : 'danger'} /> },
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
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-amber-500 to-orange-500">
              <Building2 className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight txt">Accounts</h1>
              <p className="txt-muted mt-0.5 text-[13px] font-medium">Manage customer organizations and pipeline</p>
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
              <Plus className="h-4 w-4" /> Add Account
            </button>
          </div>
        </div>

        {/* ── Filters Bar ── */}
        <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
          <SearchInput placeholder="Search accounts..." value={search} onChange={(e) => setSearch(e.target.value)} containerClassName="flex-1 sm:max-w-xs" />
          <div className="flex flex-wrap gap-2">
            <FilterSelect options={INDUSTRY_OPTIONS} value={industryFilter} onChange={(e) => setIndustryFilter(e.target.value)} />
            <FilterSelect options={STATUS_OPTIONS} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
          </div>
        </div>

        {/* ── Data Table ── */}
        <div className="min-h-[400px] flex-1">
          <div className="surface bd overflow-hidden rounded-2xl border">
            <DataTable<Account>
              columns={columns}
              data={filtered}
              rowKey={(row) => row.id}
              sortKey={sortKey}
              sortDirection={sortDir}
              onSort={handleSort}
              onRowClick={handleRowClick}
              emptyMessage="No accounts found"
            />
          </div>
        </div>
      </div>

      {/* ── Add / Edit Drawer ── */}
      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={drawerMode === 'add' ? 'Add Account' : 'Edit Account'}
        subtitle={drawerMode === 'add' ? 'Create a new customer account' : 'Update account details'}
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
          {/* Company Info */}
          <div>
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Company Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Account Name" required><FormInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></FormField>
              <FormField label="Website"><FormInput value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} /></FormField>
              <FormField label="Industry"><FormSelect options={INDUSTRY_OPTIONS.filter(o => o.value !== '')} value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} /></FormField>
              <FormField label="Company Size"><FormInput value={form.companySize} onChange={(e) => setForm({ ...form, companySize: e.target.value })} /></FormField>
              <FormField label="Annual Revenue"><FormInput value={form.annualRevenue} onChange={(e) => setForm({ ...form, annualRevenue: e.target.value })} /></FormField>
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
              <FormField label="Account Owner"><FormInput value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></FormField>
              <FormField label="Status"><FormSelect options={STATUS_OPTIONS.filter(o => o.value !== '')} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as AccountStatus })} /></FormField>
              <FormField label="Lead Source"><FormInput value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} /></FormField>
            </div>
            <div className="mt-4">
               <FormField label="Description"><FormTextarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></FormField>
            </div>
          </div>
        </div>
      </SlideDrawer>
    </>
  );
}
