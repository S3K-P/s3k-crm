'use client';

import { useState, useMemo, useCallback } from 'react';
import { Users, Plus, Download, Upload, MoreHorizontal, Pencil, Trash2, KeyRound } from 'lucide-react';
import DataTable, { type ColumnDef, type SortDirection } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import StatusBadge from '@/components/crm/shared/StatusBadge';

type UserStatus = 'Active' | 'Disabled' | 'Pending';

interface AdminUser {
  id: string;
  name: string;
  email: string;
  department: string;
  team: string;
  role: string;
  status: UserStatus;
  lastLogin: string;
}

const INITIAL_DATA: AdminUser[] = [
  { id: '1', name: 'Mike Johnson', email: 'mike@enterprise.crm', department: 'Sales', team: 'Enterprise West', role: 'Sales Manager', status: 'Active', lastLogin: 'Today, 09:30 AM' },
  { id: '2', name: 'Sarah Chen', email: 'sarah@enterprise.crm', department: 'Marketing', team: 'Demand Gen', role: 'Marketing Lead', status: 'Active', lastLogin: 'Today, 10:15 AM' },
  { id: '3', name: 'Priya Patel', email: 'priya@enterprise.crm', department: 'Sales', team: 'SMB East', role: 'Sales Rep', status: 'Active', lastLogin: 'Yesterday, 04:20 PM' },
  { id: '4', name: 'John Doe', email: 'john@enterprise.crm', department: 'Support', team: 'Tier 2', role: 'Support Agent', status: 'Disabled', lastLogin: '1 month ago' },
  { id: '5', name: 'Alex Wong', email: 'alex@enterprise.crm', department: 'Operations', team: 'RevOps', role: 'Admin', status: 'Active', lastLogin: 'Today, 08:00 AM' },
];

export default function AdminUsersPage() {
  const [data, setData] = useState<AdminUser[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<'add'|'edit'>('add');
  const [form, setForm] = useState<Partial<AdminUser>>({ status: 'Active' });
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r => r.name.toLowerCase().includes(q) || r.email.toLowerCase().includes(q));
    }
    if (sortKey && sortDir) {
      rows = [...rows].sort((a, b) => {
        const aVal = String((a as any)[sortKey]).toLowerCase();
        const bVal = String((b as any)[sortKey]).toLowerCase();
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      });
    }
    return rows;
  }, [data, search, sortKey, sortDir]);

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

  const handleSave = () => {
    if (drawerMode === 'add') {
      setData([{ ...(form as AdminUser), id: Date.now().toString(), lastLogin: 'Never' }, ...data]);
    }
    setDrawerOpen(false);
  };

  const columns: ColumnDef<AdminUser>[] = [
    {
      key: 'name', label: 'User', sortable: true,
      render: (row) => (
        <div className="flex flex-col">
          <span className="txt text-[13px] font-semibold">{row.name}</span>
          <span className="txt-faint text-[11.5px] mt-0.5">{row.email}</span>
        </div>
      ),
    },
    { key: 'department', label: 'Department', sortable: true, hideBelow: 'md', render: row => <span className="txt-muted text-[12.5px]">{row.department}</span> },
    { key: 'team', label: 'Team', sortable: true, hideBelow: 'md', render: row => <span className="txt-muted text-[12.5px]">{row.team}</span> },
    { key: 'role', label: 'Role', sortable: true, render: row => <span className="txt-muted text-[12.5px] font-medium">{row.role}</span> },
    { key: 'status', label: 'Status', sortable: true, render: row => <StatusBadge label={row.status} variant={row.status === 'Active' ? 'success' : row.status === 'Disabled' ? 'neutral' : 'warning'} /> },
    { key: 'lastLogin', label: 'Last Login', sortable: true, hideBelow: 'lg', render: row => <span className="txt-muted text-[12px]">{row.lastLogin}</span> },
    {
      key: 'actions', label: '', align: 'right',
      render: (row) => (
        <div className="relative">
          <button onClick={(e) => { e.stopPropagation(); setOpenActionId(prev => prev === row.id ? null : row.id); }} className="ctl grid h-7 w-7 place-items-center rounded-lg">
            <MoreHorizontal className="h-4 w-4" />
          </button>
          {openActionId === row.id && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setOpenActionId(null)} />
              <div className="surface bd absolute right-0 top-full z-20 mt-1 w-40 overflow-hidden rounded-xl border shadow-lg py-1">
                <button className="flex w-full items-center gap-2 px-3 py-2 text-[12.5px] font-medium hover:surface-2 text-[var(--accent)]" onClick={() => { setDrawerMode('edit'); setForm(row); setDrawerOpen(true); setOpenActionId(null); }}>
                  <Pencil className="h-3.5 w-3.5" /> Edit User
                </button>
                <button className="flex w-full items-center gap-2 px-3 py-2 text-[12.5px] font-medium hover:surface-2 txt-muted" onClick={() => setOpenActionId(null)}>
                  <KeyRound className="h-3.5 w-3.5" /> Reset Password
                </button>
                <div className="h-px w-full bg-[var(--border)] my-1" />
                <button className="flex w-full items-center gap-2 px-3 py-2 text-[12.5px] font-medium hover:surface-2 text-rose-500" onClick={() => setOpenActionId(null)}>
                  <Trash2 className="h-3.5 w-3.5" /> Disable User
                </button>
              </div>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="flex h-full flex-col space-y-5 p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-violet-600">
            <Users className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Users</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Manage active accounts and provisioning.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setDrawerMode('add'); setForm({ status: 'Active' }); setDrawerOpen(true); }} className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            <Plus className="h-4 w-4" /> Add User
          </button>
        </div>
      </div>

      <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
        <SearchInput placeholder="Search users by name or email..." value={search} onChange={e => setSearch(e.target.value)} containerClassName="flex-1 max-w-sm" />
      </div>

      <div className="surface bd overflow-hidden rounded-2xl border flex-1">
        <DataTable columns={columns} data={filtered} rowKey={row => row.id} sortKey={sortKey} sortDirection={sortDir} onSort={handleSort} onRowClick={() => {}} />
      </div>

      <SlideDrawer
        open={drawerOpen} onClose={() => setDrawerOpen(false)}
        title={drawerMode === 'add' ? 'Provision User' : 'Edit User'}
        subtitle="Manage user access and details."
        width="max-w-md"
        footer={
          <>
            <button onClick={() => setDrawerOpen(false)} className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80">Cancel</button>
            <button onClick={handleSave} className="rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>Save User</button>
          </>
        }
      >
        <div className="space-y-4">
          <FormField label="Full Name" required><FormInput value={form.name || ''} onChange={e => setForm({...form, name: e.target.value})} /></FormField>
          <FormField label="Email Address" required><FormInput type="email" value={form.email || ''} onChange={e => setForm({...form, email: e.target.value})} /></FormField>
          <div className="grid grid-cols-2 gap-4 border-t border-[var(--border)] pt-4 mt-4">
            <FormField label="Department"><FormInput value={form.department || ''} onChange={e => setForm({...form, department: e.target.value})} /></FormField>
            <FormField label="Team"><FormInput value={form.team || ''} onChange={e => setForm({...form, team: e.target.value})} /></FormField>
          </div>
          <div className="grid grid-cols-2 gap-4 border-t border-[var(--border)] pt-4 mt-4">
            <FormField label="Role" required><FormSelect options={[{value: 'Admin', label: 'Admin'}, {value: 'Sales Manager', label: 'Sales Manager'}, {value: 'Sales Rep', label: 'Sales Rep'}]} value={form.role || ''} onChange={e => setForm({...form, role: e.target.value})} /></FormField>
            <FormField label="Status" required><FormSelect options={[{value: 'Active', label: 'Active'}, {value: 'Disabled', label: 'Disabled'}]} value={form.status || ''} onChange={e => setForm({...form, status: e.target.value as UserStatus})} /></FormField>
          </div>
        </div>
      </SlideDrawer>
    </div>
  );
}
