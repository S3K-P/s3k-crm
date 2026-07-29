'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Users, Plus, Download, Upload, LayoutList, LayoutGrid,
  MoreHorizontal, Pencil, Trash2, Building2, Calendar, Phone, Mail, FileText
} from 'lucide-react';
import DataTable, { type ColumnDef, type SortDirection } from '@/components/crm/tables/DataTable';
import KanbanBoard, { type KanbanColumnDef } from '@/components/crm/kanban/KanbanBoard';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { cn } from '@/lib/utils';

/* ============================================================
   TYPES
   ============================================================ */

export type LeadStatus = 'New' | 'Contacted' | 'Qualified' | 'Proposal Sent' | 'Negotiation' | 'Converted' | 'Lost';

interface Lead {
  id: string;
  firstName: string;
  lastName: string;
  company: string;
  email: string;
  phone: string;
  source: string;
  owner: string;
  status: LeadStatus;
  aiScore: number;
  lastActivity: string;
  createdDate: string;
  industry: string;
  website: string;
  companySize: string;
  priority: string;
  expectedDealSize: string;
  notes: string;
}

type DrawerMode = 'add' | 'edit';
type ViewMode = 'table' | 'kanban';

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: Lead[] = [
  { id: '1', firstName: 'John', lastName: 'Doe', company: 'Acme Corp', email: 'john@acme.com', phone: '+1 555-0101', source: 'Website', owner: 'Sarah Chen', status: 'New', aiScore: 85, lastActivity: '2 hours ago', createdDate: '2026-07-08', industry: 'Technology', website: 'acme.com', companySize: '100-500', priority: 'High', expectedDealSize: '$50,000', notes: 'Interested in Enterprise plan.' },
  { id: '2', firstName: 'Jane', lastName: 'Smith', company: 'TechVista', email: 'jane@techvista.com', phone: '+1 555-0102', source: 'LinkedIn', owner: 'James Rodriguez', status: 'Contacted', aiScore: 92, lastActivity: '1 day ago', createdDate: '2026-07-07', industry: 'Software', website: 'techvista.com', companySize: '50-100', priority: 'Medium', expectedDealSize: '$25,000', notes: 'Needs demo.' },
  { id: '3', firstName: 'Alice', lastName: 'Johnson', company: 'Globex Ltd', email: 'alice@globex.com', phone: '+1 555-0103', source: 'Webinar', owner: 'Priya Patel', status: 'Qualified', aiScore: 78, lastActivity: '3 hours ago', createdDate: '2026-07-05', industry: 'Manufacturing', website: 'globex.com', companySize: '500+', priority: 'High', expectedDealSize: '$120,000', notes: 'Budget approved for Q3.' },
  { id: '4', firstName: 'Bob', lastName: 'Williams', company: 'Initech', email: 'bob@initech.com', phone: '+1 555-0104', source: 'Cold Calling', owner: 'Mike Johnson', status: 'Proposal Sent', aiScore: 65, lastActivity: '5 days ago', createdDate: '2026-06-28', industry: 'Services', website: 'initech.com', companySize: '10-50', priority: 'Low', expectedDealSize: '$10,000', notes: 'Reviewing proposal.' },
  { id: '5', firstName: 'Charlie', lastName: 'Brown', company: 'Stark Ind', email: 'charlie@stark.com', phone: '+1 555-0105', source: 'Exhibition', owner: 'Sarah Chen', status: 'Negotiation', aiScore: 88, lastActivity: '1 hour ago', createdDate: '2026-07-01', industry: 'Defense', website: 'stark.com', companySize: '1000+', priority: 'High', expectedDealSize: '$500,000', notes: 'Finalizing legal terms.' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'New', label: 'New' },
  { value: 'Contacted', label: 'Contacted' },
  { value: 'Qualified', label: 'Qualified' },
  { value: 'Proposal Sent', label: 'Proposal Sent' },
  { value: 'Negotiation', label: 'Negotiation' },
  { value: 'Converted', label: 'Converted' },
  { value: 'Lost', label: 'Lost' },
];

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'Website', label: 'Website' },
  { value: 'LinkedIn', label: 'LinkedIn' },
  { value: 'Webinar', label: 'Webinar' },
  { value: 'Cold Calling', label: 'Cold Calling' },
  { value: 'Exhibition', label: 'Exhibition' },
];

const EMPTY_FORM: Partial<Lead> = {
  firstName: '', lastName: '', company: '', email: '', phone: '', source: '', owner: '', status: 'New',
  industry: '', website: '', companySize: '', priority: 'Medium', expectedDealSize: '', notes: ''
};

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function LeadsPage() {
  const router = useRouter();

  /* ---- State ---- */
  const [data, setData] = useState<Lead[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('table');

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('add');
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<Lead>>(EMPTY_FORM);
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.firstName.toLowerCase().includes(q) ||
        r.lastName.toLowerCase().includes(q) ||
        r.company.toLowerCase().includes(q) ||
        r.email.toLowerCase().includes(q)
      );
    }
    if (statusFilter) rows = rows.filter(r => r.status === statusFilter);
    if (sourceFilter) rows = rows.filter(r => r.source === sourceFilter);
    
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
  }, [data, search, statusFilter, sourceFilter, sortKey, sortDir]);

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
  const handleRowClick = (row: Lead) => router.push(`/leads/${row.id}`);

  const openAdd = () => {
    setDrawerMode('add');
    setEditId(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  };

  const openEdit = (row: Lead) => {
    setDrawerMode('edit');
    setEditId(row.id);
    setForm({ ...row });
    setDrawerOpen(true);
    setOpenActionId(null);
  };

  const handleSave = () => {
    if (!form.firstName?.trim() || !form.lastName?.trim() || !form.company?.trim()) return;

    if (drawerMode === 'add') {
      const newItem: Lead = {
        ...(form as Lead),
        id: String(Date.now()),
        aiScore: Math.floor(Math.random() * 100), // Mock score
        lastActivity: 'Just now',
        createdDate: new Date().toISOString().slice(0, 10),
      };
      setData(prev => [newItem, ...prev]);
    } else if (editId) {
      setData(prev => prev.map(r => r.id === editId ? { ...r, ...(form as Lead) } : r));
    }

    setDrawerOpen(false);
  };

  const handleDelete = (id: string) => {
    setData(prev => prev.filter(r => r.id !== id));
    setOpenActionId(null);
  };

  /* ---- Table Columns ---- */
  const columns: ColumnDef<Lead>[] = [
    {
      key: 'name', label: 'Lead Name', sortable: true, minWidth: '180px',
      render: (row) => (
        <span className="txt text-[13px] font-semibold">{row.firstName} {row.lastName}</span>
      ),
    },
    { key: 'company', label: 'Company', sortable: true, render: (row) => <span className="txt">{row.company}</span> },
    { key: 'email', label: 'Email', hideBelow: 'md', render: (row) => <span className="txt-muted text-[12.5px]">{row.email}</span> },
    { key: 'phone', label: 'Phone', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px]">{row.phone}</span> },
    { key: 'source', label: 'Lead Source', hideBelow: 'lg', render: (row) => <StatusBadge label={row.source} variant="neutral" /> },
    { key: 'owner', label: 'Owner', hideBelow: 'md', render: (row) => <span className="txt-muted text-[12.5px] font-medium">{row.owner}</span> },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge label={row.status} variant={row.status === 'Converted' ? 'success' : row.status === 'Lost' ? 'danger' : 'accent'} /> },
    {
      key: 'aiScore', label: 'AI Score', sortable: true, align: 'center',
      render: (row) => (
        <span className={cn("font-display text-[14px] font-bold", row.aiScore >= 80 ? 'text-emerald-500' : row.aiScore >= 60 ? 'text-amber-500' : 'text-rose-500')}>
          {row.aiScore}
        </span>
      ),
    },
    { key: 'lastActivity', label: 'Last Activity', hideBelow: 'xl', render: (row) => <span className="txt-faint text-[12px]">{row.lastActivity}</span> },
    { key: 'createdDate', label: 'Created Date', hideBelow: 'xl', render: (row) => <span className="txt-faint text-[12px]">{row.createdDate}</span> },
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

  /* ---- Kanban Columns ---- */
  const kanbanColumns: KanbanColumnDef<Lead>[] = [
    { id: 'New', label: 'New', color: '#60a5fa' },
    { id: 'Contacted', label: 'Contacted', color: '#818cf8' },
    { id: 'Qualified', label: 'Qualified', color: '#a78bfa' },
    { id: 'Proposal Sent', label: 'Proposal Sent', color: '#c084fc' },
    { id: 'Negotiation', label: 'Negotiation', color: '#f472b6' },
    { id: 'Converted', label: 'Converted', color: '#34d399' },
    { id: 'Lost', label: 'Lost', color: '#f87171' },
  ];

  /* ---- Render ---- */
  return (
    <>
      <div className="flex h-full flex-col space-y-5 p-6 lg:p-8">
        {/* ── Page Header ── */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-500">
              <Users className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight txt">Leads</h1>
              <p className="txt-muted mt-0.5 text-[13px] font-medium">Manage and qualify prospective customers</p>
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
              <Plus className="h-4 w-4" /> Add Lead
            </button>
          </div>
        </div>

        {/* ── Filters Bar ── */}
        <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
          <SearchInput placeholder="Search leads..." value={search} onChange={(e) => setSearch(e.target.value)} containerClassName="flex-1 sm:max-w-xs" />
          <div className="flex flex-wrap gap-2">
            <FilterSelect options={STATUS_OPTIONS} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
            <FilterSelect options={SOURCE_OPTIONS} value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} />
          </div>
          <div className="ml-auto flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-1">
            <button
              onClick={() => setViewMode('table')}
              className={cn("rounded-md p-1.5 transition-colors", viewMode === 'table' ? 'bg-[var(--surface)] shadow-sm' : 'text-[var(--muted)] hover:text-[var(--text)]')}
            >
              <LayoutList className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('kanban')}
              className={cn("rounded-md p-1.5 transition-colors", viewMode === 'kanban' ? 'bg-[var(--surface)] shadow-sm' : 'text-[var(--muted)] hover:text-[var(--text)]')}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ── Data View ── */}
        <div className="min-h-[400px] flex-1">
          {viewMode === 'table' ? (
            <div className="surface bd overflow-hidden rounded-2xl border">
              <DataTable<Lead>
                columns={columns}
                data={filtered}
                rowKey={(row) => row.id}
                sortKey={sortKey}
                sortDirection={sortDir}
                onSort={handleSort}
                onRowClick={handleRowClick}
                emptyMessage="No leads found"
              />
            </div>
          ) : (
            <KanbanBoard<Lead>
              columns={kanbanColumns}
              data={filtered}
              groupBy={(lead) => lead.status}
              renderCard={(lead) => (
                <div 
                  className="surface bd cursor-pointer rounded-xl border p-3 transition-shadow hover:shadow-sm"
                  onClick={() => handleRowClick(lead)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h4 className="txt text-[13px] font-semibold">{lead.firstName} {lead.lastName}</h4>
                    <span className={cn("font-display text-[12px] font-bold", lead.aiScore >= 80 ? 'text-emerald-500' : lead.aiScore >= 60 ? 'text-amber-500' : 'text-rose-500')}>
                      {lead.aiScore}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5">
                    <Building2 className="h-3 w-3 text-[var(--faint)]" />
                    <span className="txt-muted text-[12px]">{lead.company}</span>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-[var(--border)] pt-2">
                    <div className="flex items-center gap-1.5">
                      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--surface-2)] text-[10px] font-bold text-[var(--accent)]">
                        {lead.owner.charAt(0)}
                      </div>
                      <span className="txt-faint text-[11px]">{lead.owner}</span>
                    </div>
                    <span className="txt-faint text-[10px]">{lead.lastActivity}</span>
                  </div>
                </div>
              )}
            />
          )}
        </div>
      </div>

      {/* ── Add / Edit Drawer ── */}
      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={drawerMode === 'add' ? 'Add Lead' : 'Edit Lead'}
        subtitle={drawerMode === 'add' ? 'Create a new lead profile' : 'Update lead details'}
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
              <FormField label="Email"><FormInput type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></FormField>
              <FormField label="Phone"><FormInput type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></FormField>
            </div>
          </div>
          {/* Company Info */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Company Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Company Name" required><FormInput value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></FormField>
              <FormField label="Industry"><FormInput value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} /></FormField>
              <FormField label="Website"><FormInput value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} /></FormField>
              <FormField label="Company Size"><FormInput value={form.companySize} onChange={(e) => setForm({ ...form, companySize: e.target.value })} /></FormField>
            </div>
          </div>
          {/* Sales Info */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Sales Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Lead Source"><FormSelect options={SOURCE_OPTIONS.filter(o => o.value !== '')} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} /></FormField>
              <FormField label="Status"><FormSelect options={STATUS_OPTIONS.filter(o => o.value !== '')} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as LeadStatus })} /></FormField>
              <FormField label="Priority"><FormSelect options={[{ value: 'Low', label: 'Low' }, { value: 'Medium', label: 'Medium' }, { value: 'High', label: 'High' }]} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></FormField>
              <FormField label="Expected Deal Size"><FormInput value={form.expectedDealSize} onChange={(e) => setForm({ ...form, expectedDealSize: e.target.value })} /></FormField>
              <FormField label="Assigned Owner"><FormInput value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></FormField>
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
