'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Megaphone, Plus, Download, Upload, LayoutList, LayoutGrid,
  MoreHorizontal, Pencil, Trash2, TrendingUp, Users, Target
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

export type CampaignStatus = 'Planning' | 'Active' | 'Paused' | 'Completed' | 'Cancelled';
export type CampaignType = 'Email' | 'Webinar' | 'Social Media' | 'Event' | 'Advertisement';

interface Campaign {
  id: string;
  name: string;
  type: CampaignType;
  owner: string;
  startDate: string;
  endDate: string;
  budget: string;
  expectedRevenue: string;
  leadsGenerated: number;
  opportunitiesGenerated: number;
  conversionRate: number;
  roi: string;
  progress: number;
  status: CampaignStatus;
  targetAudience: string;
  leadSource: string;
  products: string;
  notes: string;
}

type DrawerMode = 'add' | 'edit';
type ViewMode = 'table' | 'cards';

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: Campaign[] = [
  { id: '1', name: 'Q3 Enterprise Outreach', type: 'Email', owner: 'Sarah Chen', startDate: '2026-07-01', endDate: '2026-09-30', budget: '$15,000', expectedRevenue: '$150,000', leadsGenerated: 450, opportunitiesGenerated: 45, conversionRate: 10.0, roi: '185%', progress: 35, status: 'Active', targetAudience: 'CTOs, IT Directors', leadSource: 'Marketing', products: 'Enterprise Suite', notes: 'High engagement in week 1.' },
  { id: '2', name: 'AI in CRM Webinar', type: 'Webinar', owner: 'Mike Johnson', startDate: '2026-08-15', endDate: '2026-08-15', budget: '$5,000', expectedRevenue: '$50,000', leadsGenerated: 120, opportunitiesGenerated: 5, conversionRate: 4.1, roi: '45%', progress: 10, status: 'Planning', targetAudience: 'Sales Managers', leadSource: 'Webinar', products: 'AI Add-on', notes: 'Registration is open.' },
  { id: '3', name: 'SaaS Expo London', type: 'Event', owner: 'Priya Patel', startDate: '2026-06-10', endDate: '2026-06-12', budget: '$35,000', expectedRevenue: '$250,000', leadsGenerated: 850, opportunitiesGenerated: 120, conversionRate: 14.1, roi: '310%', progress: 100, status: 'Completed', targetAudience: 'Enterprise Leaders', leadSource: 'Event', products: 'Full Platform', notes: 'Very successful event.' },
  { id: '4', name: 'Summer Promo Ads', type: 'Advertisement', owner: 'Sarah Chen', startDate: '2026-06-01', endDate: '2026-08-31', budget: '$20,000', expectedRevenue: '$100,000', leadsGenerated: 210, opportunitiesGenerated: 12, conversionRate: 5.7, roi: '12%', progress: 50, status: 'Paused', targetAudience: 'Small Businesses', leadSource: 'Paid Ads', products: 'Standard Tier', notes: 'Paused due to low conversion on LinkedIn.' },
  { id: '5', name: 'Q4 Product Launch', type: 'Social Media', owner: 'Mike Johnson', startDate: '2026-10-01', endDate: '2026-11-30', budget: '$25,000', expectedRevenue: '$200,000', leadsGenerated: 0, opportunitiesGenerated: 0, conversionRate: 0, roi: '0%', progress: 0, status: 'Planning', targetAudience: 'Existing Customers', leadSource: 'Social', products: 'New Analytics Module', notes: 'Content in review.' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'Planning', label: 'Planning' },
  { value: 'Active', label: 'Active' },
  { value: 'Paused', label: 'Paused' },
  { value: 'Completed', label: 'Completed' },
  { value: 'Cancelled', label: 'Cancelled' },
];

const TYPE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'Email', label: 'Email' },
  { value: 'Webinar', label: 'Webinar' },
  { value: 'Social Media', label: 'Social Media' },
  { value: 'Event', label: 'Event' },
  { value: 'Advertisement', label: 'Advertisement' },
];

const EMPTY_FORM: Partial<Campaign> = {
  name: '', type: 'Email', owner: '', startDate: '', endDate: '', budget: '', expectedRevenue: '',
  status: 'Planning', targetAudience: '', leadSource: '', products: '', notes: ''
};

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function CampaignsPage() {
  const router = useRouter();

  /* ---- State ---- */
  const [data, setData] = useState<Campaign[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('cards');

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('add');
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<Campaign>>(EMPTY_FORM);
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.name.toLowerCase().includes(q) ||
        r.owner.toLowerCase().includes(q)
      );
    }
    if (statusFilter) rows = rows.filter(r => r.status === statusFilter);
    if (typeFilter) rows = rows.filter(r => r.type === typeFilter);
    
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
  }, [data, search, statusFilter, typeFilter, sortKey, sortDir]);

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
  const handleRowClick = (row: Campaign) => router.push(`/campaigns/${row.id}`);

  const openAdd = () => {
    setDrawerMode('add');
    setEditId(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  };

  const openEdit = (row: Campaign) => {
    setDrawerMode('edit');
    setEditId(row.id);
    setForm({ ...row });
    setDrawerOpen(true);
    setOpenActionId(null);
  };

  const handleSave = () => {
    if (!form.name?.trim() || !form.budget?.trim()) return;

    if (drawerMode === 'add') {
      const newItem: Campaign = {
        ...(form as Campaign),
        id: String(Date.now()),
        leadsGenerated: 0,
        opportunitiesGenerated: 0,
        conversionRate: 0,
        roi: '0%',
        progress: 0,
      };
      setData(prev => [newItem, ...prev]);
    } else if (editId) {
      setData(prev => prev.map(r => r.id === editId ? { ...r, ...(form as Campaign) } : r));
    }

    setDrawerOpen(false);
  };

  const handleDelete = (id: string) => {
    setData(prev => prev.filter(r => r.id !== id));
    setOpenActionId(null);
  };

  /* ---- Table Columns ---- */
  const columns: ColumnDef<Campaign>[] = [
    {
      key: 'name', label: 'Campaign Name', sortable: true, minWidth: '220px',
      render: (row) => (
        <div className="flex flex-col">
          <span className="txt text-[13px] font-semibold">{row.name}</span>
          <span className="txt-faint text-[11px] mt-0.5">{row.startDate} to {row.endDate}</span>
        </div>
      ),
    },
    { key: 'type', label: 'Type', sortable: true, hideBelow: 'sm', render: (row) => <span className="txt-muted text-[12.5px]">{row.type}</span> },
    { key: 'budget', label: 'Budget', sortable: true, hideBelow: 'md', render: (row) => <span className="font-display txt text-[13.5px] font-bold">{row.budget}</span> },
    { key: 'leadsGenerated', label: 'Leads', sortable: true, align: 'center', render: (row) => <span className="txt-muted text-[12.5px]">{row.leadsGenerated}</span> },
    { key: 'opportunitiesGenerated', label: 'Opps', sortable: true, align: 'center', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px]">{row.opportunitiesGenerated}</span> },
    { key: 'roi', label: 'ROI', sortable: true, align: 'center', hideBelow: 'xl', render: (row) => <span className="font-display text-[13px] font-bold text-emerald-500">{row.roi}</span> },
    { key: 'owner', label: 'Owner', hideBelow: 'xl', render: (row) => <span className="txt-muted text-[12.5px] font-medium">{row.owner}</span> },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge label={row.status} variant={row.status === 'Completed' ? 'neutral' : row.status === 'Active' ? 'success' : row.status === 'Paused' ? 'warning' : 'accent'} /> },
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
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-rose-500 to-orange-600">
              <Megaphone className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight txt">Campaigns</h1>
              <p className="txt-muted mt-0.5 text-[13px] font-medium">Manage marketing efforts and track pipeline ROI</p>
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
              <Plus className="h-4 w-4" /> Create Campaign
            </button>
          </div>
        </div>

        {/* ── Filters Bar ── */}
        <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
          <SearchInput placeholder="Search campaigns..." value={search} onChange={(e) => setSearch(e.target.value)} containerClassName="flex-1 sm:max-w-xs" />
          <div className="flex flex-wrap gap-2">
            <FilterSelect options={TYPE_OPTIONS} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} />
            <FilterSelect options={STATUS_OPTIONS} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
          </div>
          <div className="ml-auto flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-1">
            <button
              onClick={() => setViewMode('table')}
              className={cn("rounded-md p-1.5 transition-colors", viewMode === 'table' ? 'bg-[var(--surface)] shadow-sm' : 'text-[var(--muted)] hover:text-[var(--text)]')}
            >
              <LayoutList className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('cards')}
              className={cn("rounded-md p-1.5 transition-colors", viewMode === 'cards' ? 'bg-[var(--surface)] shadow-sm' : 'text-[var(--muted)] hover:text-[var(--text)]')}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ── Data View ── */}
        <div className="min-h-[400px] flex-1">
          {viewMode === 'table' ? (
            <div className="surface bd overflow-hidden rounded-2xl border">
              <DataTable<Campaign>
                columns={columns}
                data={filtered}
                rowKey={(row) => row.id}
                sortKey={sortKey}
                sortDirection={sortDir}
                onSort={handleSort}
                onRowClick={handleRowClick}
                emptyMessage="No campaigns found"
              />
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
               {filtered.map(campaign => (
                 <div 
                   key={campaign.id} 
                   onClick={() => handleRowClick(campaign)}
                   className="surface bd flex flex-col gap-4 rounded-2xl border p-5 transition-shadow hover:shadow-md cursor-pointer"
                 >
                   <div className="flex items-start justify-between">
                     <div>
                       <h3 className="txt text-[14px] font-bold leading-tight">{campaign.name}</h3>
                       <p className="txt-faint text-[11px] mt-1">{campaign.type} • {campaign.startDate}</p>
                     </div>
                     <StatusBadge label={campaign.status} variant={campaign.status === 'Completed' ? 'neutral' : campaign.status === 'Active' ? 'success' : campaign.status === 'Paused' ? 'warning' : 'accent'} />
                   </div>
                   
                   <div className="grid grid-cols-2 gap-3 pt-2">
                     <div>
                       <p className="txt-muted text-[10px] font-semibold uppercase tracking-wider">Budget</p>
                       <p className="font-display txt text-[14px] font-bold mt-0.5">{campaign.budget}</p>
                     </div>
                     <div>
                       <p className="txt-muted text-[10px] font-semibold uppercase tracking-wider">ROI</p>
                       <p className="font-display text-[14px] font-bold text-emerald-500 mt-0.5">{campaign.roi}</p>
                     </div>
                   </div>
                   
                   <div className="flex items-center gap-4 border-t border-[var(--border)] pt-3">
                      <div className="flex items-center gap-1.5">
                        <Users className="h-3.5 w-3.5 text-[var(--muted)]" />
                        <span className="txt text-[12px] font-semibold">{campaign.leadsGenerated}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Target className="h-3.5 w-3.5 text-[var(--muted)]" />
                        <span className="txt text-[12px] font-semibold">{campaign.opportunitiesGenerated}</span>
                      </div>
                   </div>

                   <div className="mt-auto pt-2">
                     <div className="flex items-center justify-between text-[10px] font-semibold txt-muted mb-1.5">
                       <span>Progress</span>
                       <span>{campaign.progress}%</span>
                     </div>
                     <div className="h-1.5 w-full bg-[var(--surface-2)] rounded-full overflow-hidden">
                       <div 
                         className={cn("h-full", campaign.progress === 100 ? 'bg-emerald-500' : 'bg-[var(--accent)]')} 
                         style={{ width: `${campaign.progress}%` }} 
                       />
                     </div>
                   </div>
                 </div>
               ))}
               {filtered.length === 0 && (
                 <div className="col-span-full py-12 text-center text-[13px] font-medium txt-muted">No campaigns found.</div>
               )}
            </div>
          )}
        </div>
      </div>

      {/* ── Add / Edit Drawer ── */}
      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={drawerMode === 'add' ? 'Create Campaign' : 'Edit Campaign'}
        subtitle={drawerMode === 'add' ? 'Launch a new marketing initiative' : 'Update campaign details'}
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
          {/* Info */}
          <div>
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Campaign Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Campaign Name" required className="sm:col-span-2"><FormInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Q4 Outreach" /></FormField>
              <FormField label="Campaign Type"><FormSelect options={TYPE_OPTIONS.filter(o => o.value !== '')} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as CampaignType })} /></FormField>
              <FormField label="Campaign Owner"><FormInput value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></FormField>
            </div>
            <div className="mt-4">
              <FormField label="Description"><FormTextarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></FormField>
            </div>
          </div>
          
          {/* Schedule */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Schedule & Status</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Start Date"><FormInput type="date" value={form.startDate} onChange={(e) => setForm({ ...form, startDate: e.target.value })} /></FormField>
              <FormField label="End Date"><FormInput type="date" value={form.endDate} onChange={(e) => setForm({ ...form, endDate: e.target.value })} /></FormField>
              <FormField label="Status"><FormSelect options={STATUS_OPTIONS.filter(o => o.value !== '')} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as CampaignStatus })} /></FormField>
            </div>
          </div>
          
          {/* Budget */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Budget</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Allocated Budget" required><FormInput value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} placeholder="$0.00" /></FormField>
              <FormField label="Expected Revenue"><FormInput value={form.expectedRevenue} onChange={(e) => setForm({ ...form, expectedRevenue: e.target.value })} placeholder="$0.00" /></FormField>
            </div>
          </div>
          
          {/* Audience */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Audience & Integration</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Target Audience"><FormInput value={form.targetAudience} onChange={(e) => setForm({ ...form, targetAudience: e.target.value })} placeholder="e.g. IT Managers" /></FormField>
              <FormField label="Lead Source Indicator"><FormInput value={form.leadSource} onChange={(e) => setForm({ ...form, leadSource: e.target.value })} /></FormField>
              <FormField label="Associated Products" className="sm:col-span-2"><FormInput value={form.products} onChange={(e) => setForm({ ...form, products: e.target.value })} /></FormField>
            </div>
          </div>
        </div>
      </SlideDrawer>
    </>
  );
}
