'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Target, Plus, Download, Upload, LayoutList, LayoutGrid,
  MoreHorizontal, Pencil, Trash2
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

export type OpportunityStage = 'Qualification' | 'Discovery' | 'Proposal' | 'Negotiation' | 'Contract Review' | 'Closed Won' | 'Closed Lost';

interface Opportunity {
  id: string;
  name: string;
  account: string;
  primaryContact: string;
  owner: string;
  stage: OpportunityStage;
  dealValue: string;
  winProbability: number;
  expectedCloseDate: string;
  healthScore: number;
  lastActivity: string;
  currency: string;
  forecastCategory: string;
  competitor: string;
  leadSource: string;
  products: string;
  notes: string;
}

type DrawerMode = 'add' | 'edit';
type ViewMode = 'table' | 'kanban';

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: Opportunity[] = [
  { id: '1', name: 'Enterprise Expansion - Q3', account: 'Acme Corp', primaryContact: 'Sarah Chen', owner: 'Mike Johnson', stage: 'Negotiation', dealValue: '$150,000', winProbability: 85, expectedCloseDate: '2026-09-30', healthScore: 92, lastActivity: '2 hours ago', currency: 'USD', forecastCategory: 'Commit', competitor: 'Competitor A', leadSource: 'Direct', products: 'Enterprise Suite', notes: 'Legal is reviewing the final contract.' },
  { id: '2', name: 'Global Rollout Phase 1', account: 'Globex Ltd', primaryContact: 'James Rodriguez', owner: 'Priya Patel', stage: 'Proposal', dealValue: '$75,000', winProbability: 60, expectedCloseDate: '2026-10-15', healthScore: 78, lastActivity: '1 day ago', currency: 'USD', forecastCategory: 'Best Case', competitor: 'Competitor B', leadSource: 'Partner', products: 'Analytics Add-on', notes: 'Awaiting feedback on the technical proposal.' },
  { id: '3', name: 'Security Compliance Audit', account: 'Initech', primaryContact: 'Alice Johnson', owner: 'Sarah Chen', stage: 'Discovery', dealValue: '$25,000', winProbability: 40, expectedCloseDate: '2026-11-01', healthScore: 82, lastActivity: '3 days ago', currency: 'USD', forecastCategory: 'Pipeline', competitor: 'None', leadSource: 'Inbound', products: 'Security Module', notes: 'Scheduled a deep dive session next week.' },
  { id: '4', name: 'Strategic Defense Initiative', account: 'Stark Ind', primaryContact: 'Bob Williams', owner: 'Mike Johnson', stage: 'Contract Review', dealValue: '$1,500,000', winProbability: 95, expectedCloseDate: '2026-08-15', healthScore: 98, lastActivity: 'Just now', currency: 'USD', forecastCategory: 'Commit', competitor: 'Competitor C', leadSource: 'Referral', products: 'Full Platform, Platinum Support', notes: 'Final sign-off pending from Tony Stark.' },
  { id: '5', name: 'Add-on Licenses', account: 'Acme Corp', primaryContact: 'Sarah Chen', owner: 'Mike Johnson', stage: 'Qualification', dealValue: '$10,000', winProbability: 25, expectedCloseDate: '2026-12-31', healthScore: 65, lastActivity: '2 weeks ago', currency: 'USD', forecastCategory: 'Omitted', competitor: 'None', leadSource: 'Upsell', products: 'Standard Licenses', notes: 'Early conversations.' },
];

const STAGE_OPTIONS = [
  { value: '', label: 'All Stages' },
  { value: 'Qualification', label: 'Qualification' },
  { value: 'Discovery', label: 'Discovery' },
  { value: 'Proposal', label: 'Proposal' },
  { value: 'Negotiation', label: 'Negotiation' },
  { value: 'Contract Review', label: 'Contract Review' },
  { value: 'Closed Won', label: 'Closed Won' },
  { value: 'Closed Lost', label: 'Closed Lost' },
];

const ACCOUNT_OPTIONS = [
  { value: '', label: 'All Accounts' },
  { value: 'Acme Corp', label: 'Acme Corp' },
  { value: 'Globex Ltd', label: 'Globex Ltd' },
  { value: 'Initech', label: 'Initech' },
  { value: 'Stark Ind', label: 'Stark Ind' },
];

const EMPTY_FORM: Partial<Opportunity> = {
  name: '', account: '', primaryContact: '', owner: '', stage: 'Qualification', dealValue: '',
  winProbability: 10, expectedCloseDate: '', currency: 'USD', forecastCategory: 'Pipeline',
  competitor: '', leadSource: '', products: '', notes: ''
};

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function OpportunitiesPage() {
  const router = useRouter();

  /* ---- State ---- */
  const [data, setData] = useState<Opportunity[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [stageFilter, setStageFilter] = useState('');
  const [accountFilter, setAccountFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('table');

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('add');
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<Opportunity>>(EMPTY_FORM);
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.name.toLowerCase().includes(q) ||
        r.account.toLowerCase().includes(q) ||
        r.owner.toLowerCase().includes(q)
      );
    }
    if (stageFilter) rows = rows.filter(r => r.stage === stageFilter);
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
  }, [data, search, stageFilter, accountFilter, sortKey, sortDir]);

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
  const handleRowClick = (row: Opportunity) => router.push(`/opportunities/${row.id}`);

  const openAdd = () => {
    setDrawerMode('add');
    setEditId(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  };

  const openEdit = (row: Opportunity) => {
    setDrawerMode('edit');
    setEditId(row.id);
    setForm({ ...row });
    setDrawerOpen(true);
    setOpenActionId(null);
  };

  const handleSave = () => {
    if (!form.name?.trim() || !form.account?.trim()) return;

    if (drawerMode === 'add') {
      const newItem: Opportunity = {
        ...(form as Opportunity),
        id: String(Date.now()),
        healthScore: Math.floor(Math.random() * 40) + 60, // Mock 60-100
        lastActivity: 'Just now',
      };
      setData(prev => [newItem, ...prev]);
    } else if (editId) {
      setData(prev => prev.map(r => r.id === editId ? { ...r, ...(form as Opportunity) } : r));
    }

    setDrawerOpen(false);
  };

  const handleDelete = (id: string) => {
    setData(prev => prev.filter(r => r.id !== id));
    setOpenActionId(null);
  };

  /* ---- Table Columns ---- */
  const columns: ColumnDef<Opportunity>[] = [
    {
      key: 'name', label: 'Opportunity Name', sortable: true, minWidth: '200px',
      render: (row) => <span className="txt text-[13px] font-semibold">{row.name}</span>,
    },
    { key: 'account', label: 'Account', sortable: true, render: (row) => <span className="txt-muted text-[12.5px]">{row.account}</span> },
    { key: 'dealValue', label: 'Value', sortable: true, render: (row) => <span className="font-display txt text-[13.5px] font-bold">{row.dealValue}</span> },
    { key: 'stage', label: 'Stage', sortable: true, render: (row) => <StatusBadge label={row.stage} variant="accent" /> },
    { key: 'winProbability', label: 'Prob.', sortable: true, align: 'center', render: (row) => <span className="txt-muted text-[12.5px]">{row.winProbability}%</span> },
    { key: 'expectedCloseDate', label: 'Close Date', sortable: true, hideBelow: 'md', render: (row) => <span className="txt-muted text-[12.5px]">{row.expectedCloseDate}</span> },
    { key: 'owner', label: 'Owner', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px] font-medium">{row.owner}</span> },
    {
      key: 'healthScore', label: 'AI Health', sortable: true, align: 'center', hideBelow: 'xl',
      render: (row) => (
        <span className={cn("font-display text-[14px] font-bold", row.healthScore >= 80 ? 'text-emerald-500' : row.healthScore >= 60 ? 'text-amber-500' : 'text-rose-500')}>
          {row.healthScore}
        </span>
      ),
    },
    { key: 'lastActivity', label: 'Last Activity', hideBelow: 'xl', render: (row) => <span className="txt-faint text-[12px]">{row.lastActivity}</span> },
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
  const kanbanColumns: KanbanColumnDef<Opportunity>[] = [
    { id: 'Qualification', label: 'Qualification', color: '#94a3b8' },
    { id: 'Discovery', label: 'Discovery', color: '#818cf8' },
    { id: 'Proposal', label: 'Proposal', color: '#c084fc' },
    { id: 'Negotiation', label: 'Negotiation', color: '#f472b6' },
    { id: 'Contract Review', label: 'Contract Review', color: '#fbbf24' },
    { id: 'Closed Won', label: 'Closed Won', color: '#34d399' },
    { id: 'Closed Lost', label: 'Closed Lost', color: '#f87171' },
  ];

  /* ---- Render ---- */
  return (
    <>
      <div className="flex h-full flex-col space-y-5 p-6 lg:p-8">
        {/* ── Page Header ── */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-violet-600">
              <Target className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight txt">Opportunities</h1>
              <p className="txt-muted mt-0.5 text-[13px] font-medium">Manage and forecast your sales pipeline</p>
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
              <Plus className="h-4 w-4" /> Create Opportunity
            </button>
          </div>
        </div>

        {/* ── Filters Bar ── */}
        <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
          <SearchInput placeholder="Search deals..." value={search} onChange={(e) => setSearch(e.target.value)} containerClassName="flex-1 sm:max-w-xs" />
          <div className="flex flex-wrap gap-2">
            <FilterSelect options={STAGE_OPTIONS} value={stageFilter} onChange={(e) => setStageFilter(e.target.value)} />
            <FilterSelect options={ACCOUNT_OPTIONS} value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)} />
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
              <DataTable<Opportunity>
                columns={columns}
                data={filtered}
                rowKey={(row) => row.id}
                sortKey={sortKey}
                sortDirection={sortDir}
                onSort={handleSort}
                onRowClick={handleRowClick}
                emptyMessage="No opportunities found"
              />
            </div>
          ) : (
            <KanbanBoard<Opportunity>
              columns={kanbanColumns}
              data={filtered}
              groupBy={(opp) => opp.stage}
              renderCard={(opp) => (
                <div 
                  className="surface bd cursor-pointer rounded-xl border p-3 transition-shadow hover:shadow-sm"
                  onClick={() => handleRowClick(opp)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h4 className="txt text-[13px] font-semibold leading-snug">{opp.name}</h4>
                    <span className={cn("font-display text-[12px] font-bold", opp.healthScore >= 80 ? 'text-emerald-500' : opp.healthScore >= 60 ? 'text-amber-500' : 'text-rose-500')}>
                      {opp.healthScore}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-col gap-1">
                    <span className="txt-muted text-[12px] font-medium">{opp.account}</span>
                    <span className="font-display txt text-[14px] font-bold">{opp.dealValue}</span>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-[var(--border)] pt-2">
                    <div className="flex items-center gap-1.5">
                      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--surface-2)] text-[10px] font-bold text-[var(--accent)]">
                        {opp.owner.charAt(0)}
                      </div>
                    </div>
                    <span className="txt-faint text-[10px]">{opp.expectedCloseDate}</span>
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
        title={drawerMode === 'add' ? 'Create Opportunity' : 'Edit Opportunity'}
        subtitle={drawerMode === 'add' ? 'Log a new deal in the pipeline' : 'Update deal details'}
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
          {/* Opportunity Details */}
          <div>
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Opportunity Details</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Opportunity Name" required className="sm:col-span-2"><FormInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Acme Corp - Enterprise Expansion" /></FormField>
              <FormField label="Related Account" required><FormSelect options={ACCOUNT_OPTIONS.filter(o => o.value !== '')} value={form.account} onChange={(e) => setForm({ ...form, account: e.target.value })} /></FormField>
              <FormField label="Primary Contact"><FormInput value={form.primaryContact} onChange={(e) => setForm({ ...form, primaryContact: e.target.value })} /></FormField>
              <FormField label="Opportunity Owner"><FormInput value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></FormField>
            </div>
          </div>
          
          {/* Deal Info */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Deal Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Deal Value"><FormInput value={form.dealValue} onChange={(e) => setForm({ ...form, dealValue: e.target.value })} placeholder="e.g. $50,000" /></FormField>
              <FormField label="Currency"><FormInput value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} /></FormField>
              <FormField label="Stage"><FormSelect options={STAGE_OPTIONS.filter(o => o.value !== '')} value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value as OpportunityStage })} /></FormField>
              <FormField label="Probability (%)"><FormInput type="number" min="0" max="100" value={form.winProbability} onChange={(e) => setForm({ ...form, winProbability: Number(e.target.value) })} /></FormField>
              <FormField label="Expected Close Date"><FormInput type="date" value={form.expectedCloseDate} onChange={(e) => setForm({ ...form, expectedCloseDate: e.target.value })} /></FormField>
              <FormField label="Forecast Category"><FormSelect options={[{value:'Pipeline',label:'Pipeline'},{value:'Best Case',label:'Best Case'},{value:'Commit',label:'Commit'},{value:'Omitted',label:'Omitted'},{value:'Closed',label:'Closed'}]} value={form.forecastCategory} onChange={(e) => setForm({ ...form, forecastCategory: e.target.value })} /></FormField>
            </div>
          </div>
          
          {/* Additional Details */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Additional Details</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Competitor"><FormInput value={form.competitor} onChange={(e) => setForm({ ...form, competitor: e.target.value })} /></FormField>
              <FormField label="Lead Source"><FormInput value={form.leadSource} onChange={(e) => setForm({ ...form, leadSource: e.target.value })} /></FormField>
              <FormField label="Products / Services" className="sm:col-span-2"><FormInput value={form.products} onChange={(e) => setForm({ ...form, products: e.target.value })} /></FormField>
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
