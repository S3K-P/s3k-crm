'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Calendar as CalendarIcon, Plus, Download, Upload, LayoutList, CalendarDays,
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

export type MeetingStatus = 'Scheduled' | 'Completed' | 'Cancelled' | 'Rescheduled';
export type MeetingType = 'Online' | 'In Person' | 'Call';

interface Meeting {
  id: string;
  title: string;
  type: MeetingType;
  date: string;
  startTime: string;
  endTime: string;
  participants: string;
  account: string;
  contact: string;
  opportunity: string;
  internalParticipants: string;
  owner: string;
  location: string;
  link: string;
  agenda: string;
  notes: string;
  reminder: string;
  reminderTime: string;
  reminderMethod: string;
  status: MeetingStatus;
}

type DrawerMode = 'add' | 'edit';
type ViewMode = 'table' | 'calendar';

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: Meeting[] = [
  { id: '1', title: 'Q3 Enterprise Proposal Review', type: 'Online', date: '2026-07-15', startTime: '10:00 AM', endTime: '11:00 AM', participants: 'Sarah Chen, John Doe', account: 'Acme Corp', contact: 'Sarah Chen', opportunity: 'Enterprise Expansion - Q3', internalParticipants: 'Mike Johnson', owner: 'Mike Johnson', location: 'Zoom', link: 'https://zoom.us/j/123456', agenda: 'Review final pricing and MSA terms.', notes: '', reminder: 'Yes', reminderTime: '15 mins', reminderMethod: 'Email', status: 'Scheduled' },
  { id: '2', title: 'Discovery Call - New Requirements', type: 'Online', date: '2026-07-12', startTime: '02:00 PM', endTime: '03:00 PM', participants: 'James Rodriguez', account: 'Globex Ltd', contact: 'James Rodriguez', opportunity: 'Global Rollout Phase 1', internalParticipants: 'Priya Patel, Sam Smith', owner: 'Priya Patel', location: 'Google Meet', link: 'https://meet.google.com/abc', agenda: 'Understand phase 1 technical requirements.', notes: 'Client requested specific security docs.', reminder: 'Yes', reminderTime: '10 mins', reminderMethod: 'Notification', status: 'Completed' },
  { id: '3', title: 'Security Audit Kickoff', type: 'In Person', date: '2026-07-18', startTime: '09:00 AM', endTime: '12:00 PM', participants: 'Alice Johnson, Bob Williams', account: 'Initech', contact: 'Alice Johnson', opportunity: 'Security Compliance Audit', internalParticipants: 'Sarah Chen', owner: 'Sarah Chen', location: 'HQ Office - Room A', link: '', agenda: 'Onsite audit initiation.', notes: '', reminder: 'Yes', reminderTime: '1 day', reminderMethod: 'Email', status: 'Scheduled' },
  { id: '4', title: 'Monthly Sync', type: 'Call', date: '2026-07-10', startTime: '11:30 AM', endTime: '12:00 PM', participants: 'Tony Stark', account: 'Stark Ind', contact: 'Bob Williams', opportunity: 'Strategic Defense Initiative', internalParticipants: 'Mike Johnson', owner: 'Mike Johnson', location: 'Phone', link: '', agenda: 'Regular check-in.', notes: 'Tony was happy with the progress.', reminder: 'No', reminderTime: '', reminderMethod: '', status: 'Completed' },
  { id: '5', title: 'Contract Negotiation', type: 'Online', date: '2026-07-20', startTime: '01:00 PM', endTime: '02:30 PM', participants: 'Sarah Chen, Legal Team', account: 'Acme Corp', contact: 'Sarah Chen', opportunity: 'Enterprise Expansion - Q3', internalParticipants: 'Mike Johnson, Legal', owner: 'Mike Johnson', location: 'Teams', link: 'https://teams.microsoft.com', agenda: 'Finalize terms.', notes: '', reminder: 'Yes', reminderTime: '1 hour', reminderMethod: 'Email', status: 'Scheduled' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'Scheduled', label: 'Scheduled' },
  { value: 'Completed', label: 'Completed' },
  { value: 'Cancelled', label: 'Cancelled' },
  { value: 'Rescheduled', label: 'Rescheduled' },
];

const TYPE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'Online', label: 'Online' },
  { value: 'In Person', label: 'In Person' },
  { value: 'Call', label: 'Call' },
];

const EMPTY_FORM: Partial<Meeting> = {
  title: '', type: 'Online', date: '', startTime: '', endTime: '', participants: '',
  account: '', contact: '', opportunity: '', internalParticipants: '', owner: '',
  location: '', link: '', agenda: '', notes: '', reminder: 'Yes', reminderTime: '15 mins', reminderMethod: 'Email', status: 'Scheduled'
};

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function MeetingsPage() {
  const router = useRouter();

  /* ---- State ---- */
  const [data, setData] = useState<Meeting[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('table');

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('add');
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<Partial<Meeting>>(EMPTY_FORM);
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.title.toLowerCase().includes(q) ||
        r.account.toLowerCase().includes(q) ||
        r.participants.toLowerCase().includes(q)
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
  const handleRowClick = (row: Meeting) => router.push(`/meetings/${row.id}`);

  const openAdd = () => {
    setDrawerMode('add');
    setEditId(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  };

  const openEdit = (row: Meeting) => {
    setDrawerMode('edit');
    setEditId(row.id);
    setForm({ ...row });
    setDrawerOpen(true);
    setOpenActionId(null);
  };

  const handleSave = () => {
    if (!form.title?.trim() || !form.date?.trim()) return;

    if (drawerMode === 'add') {
      const newItem: Meeting = {
        ...(form as Meeting),
        id: String(Date.now()),
      };
      setData(prev => [newItem, ...prev]);
    } else if (editId) {
      setData(prev => prev.map(r => r.id === editId ? { ...r, ...(form as Meeting) } : r));
    }

    setDrawerOpen(false);
  };

  const handleDelete = (id: string) => {
    setData(prev => prev.filter(r => r.id !== id));
    setOpenActionId(null);
  };

  /* ---- Table Columns ---- */
  const columns: ColumnDef<Meeting>[] = [
    {
      key: 'title', label: 'Meeting Title', sortable: true, minWidth: '220px',
      render: (row) => (
        <div className="flex flex-col">
          <span className="txt text-[13px] font-semibold">{row.title}</span>
          <span className="txt-faint text-[11px] mt-0.5">{row.date} • {row.startTime} - {row.endTime}</span>
        </div>
      ),
    },
    { key: 'account', label: 'Account', sortable: true, hideBelow: 'md', render: (row) => <span className="txt-muted text-[12.5px]">{row.account}</span> },
    { key: 'participants', label: 'Participants', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px] truncate max-w-[150px] inline-block">{row.participants}</span> },
    { key: 'owner', label: 'Owner', hideBelow: 'xl', render: (row) => <span className="txt-muted text-[12.5px] font-medium">{row.owner}</span> },
    { key: 'type', label: 'Type', sortable: true, hideBelow: 'sm', render: (row) => <span className="txt-muted text-[12.5px]">{row.type}</span> },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge label={row.status} variant={row.status === 'Completed' ? 'success' : row.status === 'Scheduled' ? 'accent' : row.status === 'Cancelled' ? 'danger' : 'warning'} /> },
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
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
              <CalendarIcon className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight txt">Meetings</h1>
              <p className="txt-muted mt-0.5 text-[13px] font-medium">Schedule and manage customer interactions</p>
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
              <Plus className="h-4 w-4" /> Schedule Meeting
            </button>
          </div>
        </div>

        {/* ── Filters Bar ── */}
        <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
          <SearchInput placeholder="Search meetings..." value={search} onChange={(e) => setSearch(e.target.value)} containerClassName="flex-1 sm:max-w-xs" />
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
              onClick={() => setViewMode('calendar')}
              className={cn("rounded-md p-1.5 transition-colors", viewMode === 'calendar' ? 'bg-[var(--surface)] shadow-sm' : 'text-[var(--muted)] hover:text-[var(--text)]')}
            >
              <CalendarDays className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ── Data View ── */}
        <div className="min-h-[400px] flex-1">
          {viewMode === 'table' ? (
            <div className="surface bd overflow-hidden rounded-2xl border">
              <DataTable<Meeting>
                columns={columns}
                data={filtered}
                rowKey={(row) => row.id}
                sortKey={sortKey}
                sortDirection={sortDir}
                onSort={handleSort}
                onRowClick={handleRowClick}
                emptyMessage="No meetings found"
              />
            </div>
          ) : (
            <div className="surface bd rounded-2xl border p-5 min-h-[500px]">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display txt text-[18px] font-bold">July 2026</h3>
                <div className="flex gap-2">
                   <button className="ctl px-3 py-1 text-[12px] font-semibold rounded-md">Prev</button>
                   <button className="ctl px-3 py-1 text-[12px] font-semibold rounded-md">Next</button>
                </div>
              </div>
              <div className="grid grid-cols-7 gap-px bg-[var(--border)] rounded-lg overflow-hidden border border-[var(--border)]">
                 {/* Days Header */}
                 {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                   <div key={day} className="bg-[var(--surface-2)] py-2 text-center text-[12px] font-bold txt-muted uppercase">{day}</div>
                 ))}
                 
                 {/* Calendar Grid (Mock 5 weeks for July) */}
                 {Array.from({ length: 35 }).map((_, i) => {
                   const dayNum = i - 2; // offset for start of month
                   const isValidDay = dayNum > 0 && dayNum <= 31;
                   const dateStr = isValidDay ? `2026-07-${dayNum.toString().padStart(2, '0')}` : '';
                   const dayMeetings = filtered.filter(m => m.date === dateStr);
                   
                   return (
                     <div key={i} className="bg-[var(--surface)] min-h-[100px] p-2 hover:bg-[var(--surface-2)] transition-colors">
                       {isValidDay && (
                         <>
                           <span className="text-[12px] font-semibold txt-muted">{dayNum}</span>
                           <div className="mt-1 flex flex-col gap-1">
                             {dayMeetings.map(m => (
                               <div 
                                 key={m.id} 
                                 onClick={() => handleRowClick(m)}
                                 className="text-[10px] p-1 rounded bg-[var(--accent)] text-white truncate cursor-pointer hover:opacity-80 shadow-sm"
                               >
                                 {m.startTime} - {m.title}
                               </div>
                             ))}
                           </div>
                         </>
                       )}
                     </div>
                   );
                 })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Add / Edit Drawer ── */}
      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={drawerMode === 'add' ? 'Schedule Meeting' : 'Edit Meeting'}
        subtitle={drawerMode === 'add' ? 'Set up a new meeting' : 'Update meeting details'}
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
          {/* Meeting Info */}
          <div>
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Meeting Information</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Meeting Title" required className="sm:col-span-2"><FormInput value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Discovery Call" /></FormField>
              <FormField label="Meeting Type"><FormSelect options={TYPE_OPTIONS.filter(o => o.value !== '')} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as MeetingType })} /></FormField>
              <FormField label="Date" required><FormInput type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></FormField>
              <FormField label="Start Time"><FormInput type="time" value={form.startTime} onChange={(e) => setForm({ ...form, startTime: e.target.value })} /></FormField>
              <FormField label="End Time"><FormInput type="time" value={form.endTime} onChange={(e) => setForm({ ...form, endTime: e.target.value })} /></FormField>
            </div>
          </div>
          
          {/* Related Records */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Participants & Records</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Participants (External)" className="sm:col-span-2"><FormInput value={form.participants} onChange={(e) => setForm({ ...form, participants: e.target.value })} placeholder="Client names..." /></FormField>
              <FormField label="Related Account"><FormInput value={form.account} onChange={(e) => setForm({ ...form, account: e.target.value })} /></FormField>
              <FormField label="Related Opportunity"><FormInput value={form.opportunity} onChange={(e) => setForm({ ...form, opportunity: e.target.value })} /></FormField>
              <FormField label="Internal Participants"><FormInput value={form.internalParticipants} onChange={(e) => setForm({ ...form, internalParticipants: e.target.value })} /></FormField>
              <FormField label="Meeting Owner"><FormInput value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></FormField>
            </div>
          </div>
          
          {/* Details */}
          <div className="border-t border-[var(--border)] pt-6">
            <h3 className="txt mb-3 text-[14px] font-bold uppercase tracking-wide">Meeting Details</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Location"><FormInput value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Zoom, Office, etc." /></FormField>
              <FormField label="Meeting Link"><FormInput value={form.link} onChange={(e) => setForm({ ...form, link: e.target.value })} placeholder="https://..." /></FormField>
              <FormField label="Status"><FormSelect options={STATUS_OPTIONS.filter(o => o.value !== '')} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as MeetingStatus })} /></FormField>
            </div>
            <div className="mt-4">
              <FormField label="Agenda"><FormTextarea value={form.agenda} onChange={(e) => setForm({ ...form, agenda: e.target.value })} /></FormField>
            </div>
          </div>
        </div>
      </SlideDrawer>
    </>
  );
}
