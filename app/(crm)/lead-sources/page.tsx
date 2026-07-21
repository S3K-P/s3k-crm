'use client';

import { useState, useMemo, useCallback } from 'react';
import {
  Globe, Plus, Pencil, Trash2, MoreHorizontal,
} from 'lucide-react';
import DataTable, { type ColumnDef, type SortDirection } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';

/* ============================================================
   TYPES
   ============================================================ */

interface LeadSource {
  id: string;
  name: string;
  category: string;
  description: string;
  leadCount: number;
  status: 'Active' | 'Inactive';
  createdBy: string;
  lastUpdated: string;
}

type DrawerMode = 'add' | 'edit';

interface DrawerForm {
  name: string;
  category: string;
  description: string;
  status: 'Active' | 'Inactive';
}

const EMPTY_FORM: DrawerForm = {
  name: '',
  category: '',
  description: '',
  status: 'Active',
};

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: LeadSource[] = [
  { id: '1', name: 'Website',            category: 'Digital',        description: 'Inbound leads from the company website contact forms and landing pages',        leadCount: 142, status: 'Active',   createdBy: 'Admin',         lastUpdated: '2026-07-08' },
  { id: '2', name: 'LinkedIn',           category: 'Social Media',   description: 'Leads generated through LinkedIn outreach and InMail campaigns',                leadCount: 89,  status: 'Active',   createdBy: 'Sarah Chen',    lastUpdated: '2026-07-07' },
  { id: '3', name: 'Channel Partner',    category: 'Partnership',    description: 'Referrals from certified channel partners and reseller network',                leadCount: 56,  status: 'Active',   createdBy: 'James Rodriguez', lastUpdated: '2026-07-06' },
  { id: '4', name: 'Employee Referral',  category: 'Internal',       description: 'Leads referred by internal employees through the referral program',             leadCount: 34,  status: 'Active',   createdBy: 'Admin',         lastUpdated: '2026-07-05' },
  { id: '5', name: 'Webinar',            category: 'Digital',        description: 'Leads captured from webinar registrations and live event attendees',             leadCount: 67,  status: 'Active',   createdBy: 'Priya Patel',   lastUpdated: '2026-07-04' },
  { id: '6', name: 'Email Campaign',     category: 'Marketing',      description: 'Leads generated from targeted email drip campaigns and newsletters',            leadCount: 112, status: 'Active',   createdBy: 'Sarah Chen',    lastUpdated: '2026-07-03' },
  { id: '7', name: 'Cold Calling',       category: 'Outbound',       description: 'Outbound sales development through phone-based prospecting',                    leadCount: 45,  status: 'Inactive', createdBy: 'Mike Johnson',  lastUpdated: '2026-06-28' },
  { id: '8', name: 'Exhibition',         category: 'Events',         description: 'Leads scanned and collected at trade shows, expos, and industry exhibitions',    leadCount: 78,  status: 'Active',   createdBy: 'James Rodriguez', lastUpdated: '2026-07-01' },
  { id: '9', name: 'Google Ads',         category: 'Digital',        description: 'Pay-per-click leads from Google search and display advertising campaigns',      leadCount: 95,  status: 'Active',   createdBy: 'Priya Patel',   lastUpdated: '2026-07-07' },
  { id: '10', name: 'Industry Event',    category: 'Events',         description: 'Contacts gathered at conferences, meetups, and sponsored industry events',      leadCount: 23,  status: 'Inactive', createdBy: 'Admin',         lastUpdated: '2026-06-20' },
];

const CATEGORY_OPTIONS = [
  { value: '',            label: 'All Categories' },
  { value: 'Digital',     label: 'Digital' },
  { value: 'Social Media', label: 'Social Media' },
  { value: 'Partnership', label: 'Partnership' },
  { value: 'Internal',   label: 'Internal' },
  { value: 'Marketing',  label: 'Marketing' },
  { value: 'Outbound',   label: 'Outbound' },
  { value: 'Events',     label: 'Events' },
];

const STATUS_OPTIONS = [
  { value: '',         label: 'All Status' },
  { value: 'Active',   label: 'Active' },
  { value: 'Inactive', label: 'Inactive' },
];

const CATEGORY_FORM_OPTIONS = CATEGORY_OPTIONS.filter(o => o.value !== '');
const STATUS_FORM_OPTIONS = [
  { value: 'Active',   label: 'Active' },
  { value: 'Inactive', label: 'Inactive' },
];

/* ============================================================
   LEAD SOURCES PAGE
   ============================================================ */

export default function LeadSourcesPage() {
  /* ---- State ---- */
  const [data, setData] = useState<LeadSource[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('add');
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<DrawerForm>(EMPTY_FORM);

  // Actions dropdown
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;

    // Search
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.name.toLowerCase().includes(q) ||
        r.category.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.createdBy.toLowerCase().includes(q)
      );
    }

    // Category
    if (categoryFilter) {
      rows = rows.filter(r => r.category === categoryFilter);
    }

    // Status
    if (statusFilter) {
      rows = rows.filter(r => r.status === statusFilter);
    }

    // Sort
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
  }, [data, search, categoryFilter, statusFilter, sortKey, sortDir]);

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

  /* ---- Drawer handlers ---- */
  const openAdd = () => {
    setDrawerMode('add');
    setEditId(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  };

  const openEdit = (row: LeadSource) => {
    setDrawerMode('edit');
    setEditId(row.id);
    setForm({
      name: row.name,
      category: row.category,
      description: row.description,
      status: row.status,
    });
    setDrawerOpen(true);
    setOpenActionId(null);
  };

  const handleSave = () => {
    if (!form.name.trim() || !form.category) return;

    if (drawerMode === 'add') {
      const newItem: LeadSource = {
        id: String(Date.now()),
        name: form.name,
        category: form.category,
        description: form.description,
        leadCount: 0,
        status: form.status,
        createdBy: 'Current User',
        lastUpdated: new Date().toISOString().slice(0, 10),
      };
      setData(prev => [newItem, ...prev]);
    } else if (editId) {
      setData(prev =>
        prev.map(r =>
          r.id === editId
            ? { ...r, name: form.name, category: form.category, description: form.description, status: form.status, lastUpdated: new Date().toISOString().slice(0, 10) }
            : r,
        ),
      );
    }

    setDrawerOpen(false);
    setForm(EMPTY_FORM);
  };

  const handleDelete = (id: string) => {
    setData(prev => prev.filter(r => r.id !== id));
    setOpenActionId(null);
  };

  /* ---- Table columns ---- */
  const columns: ColumnDef<LeadSource>[] = [
    {
      key: 'name',
      label: 'Source Name',
      sortable: true,
      minWidth: '160px',
      render: (row) => (
        <span className="txt text-[13px] font-semibold">{row.name}</span>
      ),
    },
    {
      key: 'category',
      label: 'Category',
      sortable: true,
      render: (row) => (
        <StatusBadge label={row.category} variant="accent" />
      ),
    },
    {
      key: 'description',
      label: 'Description',
      hideBelow: 'lg',
      minWidth: '200px',
      render: (row) => (
        <span className="txt-muted line-clamp-1 text-[12.5px]">{row.description}</span>
      ),
    },
    {
      key: 'leadCount',
      label: 'Lead Count',
      sortable: true,
      align: 'center',
      render: (row) => (
        <span className="txt font-display text-[14px] font-bold">{row.leadCount}</span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (row) => (
        <StatusBadge
          label={row.status}
          variant={row.status === 'Active' ? 'success' : 'neutral'}
        />
      ),
    },
    {
      key: 'createdBy',
      label: 'Created By',
      hideBelow: 'md',
      render: (row) => (
        <span className="txt-muted text-[12.5px] font-medium">{row.createdBy}</span>
      ),
    },
    {
      key: 'lastUpdated',
      label: 'Last Updated',
      sortable: true,
      hideBelow: 'md',
      render: (row) => (
        <span className="txt-faint text-[12.5px]">{row.lastUpdated}</span>
      ),
    },
    {
      key: 'actions',
      label: '',
      align: 'right',
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
              <div className="fixed inset-0 z-10" onClick={() => setOpenActionId(null)} />
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
      <div className="space-y-5 p-6 lg:p-8">
        {/* ── Page Header ── */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
              <Globe className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1
                className="font-display text-[22px] font-extrabold leading-tight tracking-tight"
                style={{ color: 'var(--text)' }}
              >
                Lead Sources
              </h1>
              <p className="txt-muted mt-0.5 text-[13px] font-medium">
                Manage the sources from which leads are captured into your CRM
              </p>
            </div>
          </div>

          <button
            onClick={openAdd}
            className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <Plus className="h-4 w-4" />
            Add Lead Source
          </button>
        </div>

        {/* ── Filters Bar ── */}
        <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
          <SearchInput
            placeholder="Search sources..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            containerClassName="flex-1 sm:max-w-xs"
          />
          <div className="flex flex-wrap gap-2">
            <FilterSelect
              options={CATEGORY_OPTIONS}
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            />
            <FilterSelect
              options={STATUS_OPTIONS}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            />
          </div>
          <span className="txt-faint ml-auto text-[12px] font-medium">
            {filtered.length} source{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>

        {/* ── Data Table ── */}
        <div className="surface bd overflow-hidden rounded-2xl border">
          <DataTable<LeadSource>
            columns={columns}
            data={filtered}
            rowKey={(row) => row.id}
            sortKey={sortKey}
            sortDirection={sortDir}
            onSort={handleSort}
            onRowClick={openEdit}
            emptyMessage="No lead sources found — try adjusting your filters"
          />
        </div>
      </div>

      {/* ── Add / Edit Drawer ── */}
      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={drawerMode === 'add' ? 'Add Lead Source' : 'Edit Lead Source'}
        subtitle={drawerMode === 'add' ? 'Create a new lead source for your CRM' : 'Update lead source details'}
        footer={
          <>
            <button
              onClick={() => setDrawerOpen(false)}
              className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              {drawerMode === 'add' ? 'Save' : 'Update'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <FormField label="Source Name" htmlFor="source-name" required>
            <FormInput
              id="source-name"
              placeholder="e.g. Website, LinkedIn, Referral"
              value={form.name}
              onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
            />
          </FormField>

          <FormField label="Category" htmlFor="source-category" required>
            <FormSelect
              id="source-category"
              placeholder="Select a category"
              options={CATEGORY_FORM_OPTIONS}
              value={form.category}
              onChange={(e) => setForm(f => ({ ...f, category: e.target.value }))}
            />
          </FormField>

          <FormField label="Description" htmlFor="source-description">
            <FormTextarea
              id="source-description"
              placeholder="Brief description of this lead source"
              value={form.description}
              onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </FormField>

          <FormField label="Status" htmlFor="source-status">
            <FormSelect
              id="source-status"
              options={STATUS_FORM_OPTIONS}
              value={form.status}
              onChange={(e) => setForm(f => ({ ...f, status: e.target.value as 'Active' | 'Inactive' }))}
            />
          </FormField>
        </div>
      </SlideDrawer>
    </>
  );
}
