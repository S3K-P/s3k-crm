'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  ListChecks, Search, LayoutList, ListOrdered, MoreHorizontal, ArrowRight,
  TrendingUp, Users, Target, UserCheck
} from 'lucide-react';
import DataTable, { type ColumnDef, type SortDirection } from '@/components/crm/tables/DataTable';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { cn } from '@/lib/utils';

/* ============================================================
   TYPES
   ============================================================ */

export type QualificationStatus = 'Unqualified' | 'In Review' | 'Qualified' | 'Disqualified';
export type Priority = 'High' | 'Medium' | 'Low';

interface QualLead {
  id: string;
  leadName: string;
  company: string;
  source: string;
  status: QualificationStatus;
  budget: string;
  authority: string;
  need: string;
  timeline: string;
  aiScore: number;
  recommendation: string;
  owner: string;
  createdDate: string;
  priority: Priority;
}

type ViewMode = 'table' | 'queue';

/* ============================================================
   MOCK DATA
   ============================================================ */

const INITIAL_DATA: QualLead[] = [
  { id: '1', leadName: 'Alice Johnson', company: 'TechCorp Inc.', source: 'Webinar', status: 'In Review', budget: 'Pending', authority: 'Confirmed', need: 'Pending', timeline: 'Q3', aiScore: 85, recommendation: 'Fast-track discovery', owner: 'Mike Johnson', createdDate: '2026-07-08', priority: 'High' },
  { id: '2', leadName: 'Bob Williams', company: 'Globex Ltd', source: 'Website', status: 'Unqualified', budget: 'Unknown', authority: 'Unknown', need: 'Unknown', timeline: 'Unknown', aiScore: 45, recommendation: 'Nurture via email', owner: 'Unassigned', createdDate: '2026-07-09', priority: 'Low' },
  { id: '3', leadName: 'Sarah Chen', company: 'Acme Corp', source: 'Referral', status: 'Qualified', budget: 'Confirmed', authority: 'Confirmed', need: 'Confirmed', timeline: 'Immediate', aiScore: 95, recommendation: 'Convert to Opp', owner: 'Sarah Chen', createdDate: '2026-07-05', priority: 'High' },
  { id: '4', leadName: 'David Lee', company: 'Initech', source: 'Cold Call', status: 'In Review', budget: 'Confirmed', authority: 'Pending', need: 'Confirmed', timeline: 'Q4', aiScore: 72, recommendation: 'Identify Decision Maker', owner: 'Priya Patel', createdDate: '2026-07-07', priority: 'Medium' },
  { id: '5', leadName: 'Emily Davis', company: 'Stark Ind', source: 'Event', status: 'Disqualified', budget: 'No Budget', authority: 'Confirmed', need: 'None', timeline: 'N/A', aiScore: 20, recommendation: 'Drop', owner: 'Mike Johnson', createdDate: '2026-07-01', priority: 'Low' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'Unqualified', label: 'Unqualified' },
  { value: 'In Review', label: 'In Review' },
  { value: 'Qualified', label: 'Qualified' },
  { value: 'Disqualified', label: 'Disqualified' },
];

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'Website', label: 'Website' },
  { value: 'Webinar', label: 'Webinar' },
  { value: 'Referral', label: 'Referral' },
  { value: 'Cold Call', label: 'Cold Call' },
  { value: 'Event', label: 'Event' },
];

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function QualificationPage() {
  const router = useRouter();

  /* ---- State ---- */
  const [data, setData] = useState<QualLead[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('queue');

  /* ---- Filtering + sorting ---- */
  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r =>
        r.leadName.toLowerCase().includes(q) ||
        r.company.toLowerCase().includes(q)
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
    } else if (viewMode === 'queue') {
      // Default queue sort: priority (High > Medium > Low), then AI score (desc)
      const priorityWeight: Record<Priority, number> = { High: 3, Medium: 2, Low: 1 };
      rows = [...rows].sort((a, b) => {
        if (priorityWeight[a.priority] !== priorityWeight[b.priority]) {
           return priorityWeight[b.priority] - priorityWeight[a.priority];
        }
        return b.aiScore - a.aiScore;
      });
    }
    return rows;
  }, [data, search, statusFilter, sourceFilter, sortKey, sortDir, viewMode]);

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
  const handleRowClick = (row: QualLead) => router.push(`/qualification/${row.id}`);

  /* ---- Table Columns ---- */
  const columns: ColumnDef<QualLead>[] = [
    {
      key: 'leadName', label: 'Lead', sortable: true, minWidth: '200px',
      render: (row) => (
        <div className="flex flex-col">
          <span className="txt text-[13px] font-semibold">{row.leadName}</span>
          <span className="txt-faint text-[11px] mt-0.5">{row.company}</span>
        </div>
      ),
    },
    { key: 'source', label: 'Source', sortable: true, hideBelow: 'sm', render: (row) => <span className="txt-muted text-[12.5px]">{row.source}</span> },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge label={row.status} variant={row.status === 'Qualified' ? 'success' : row.status === 'In Review' ? 'accent' : row.status === 'Disqualified' ? 'danger' : 'neutral'} /> },
    { key: 'budget', label: 'Budget', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px]">{row.budget}</span> },
    { key: 'authority', label: 'Authority', hideBelow: 'lg', render: (row) => <span className="txt-muted text-[12.5px]">{row.authority}</span> },
    { key: 'need', label: 'Need', hideBelow: 'xl', render: (row) => <span className="txt-muted text-[12.5px]">{row.need}</span> },
    { key: 'timeline', label: 'Timeline', hideBelow: 'xl', render: (row) => <span className="txt-muted text-[12.5px]">{row.timeline}</span> },
    { 
      key: 'aiScore', label: 'AI Score', sortable: true, align: 'center', 
      render: (row) => (
        <span className={cn("font-display text-[14px] font-bold", row.aiScore >= 80 ? 'text-emerald-500' : row.aiScore >= 50 ? 'text-amber-500' : 'text-rose-500')}>
          {row.aiScore}
        </span>
      ) 
    },
    { key: 'recommendation', label: 'Recommendation', hideBelow: 'md', render: (row) => <span className="txt-muted text-[12px] italic">{row.recommendation}</span> },
    {
      key: 'actions', label: '', align: 'right',
      render: (row) => (
        <button
          onClick={(e) => { e.stopPropagation(); handleRowClick(row); }}
          className="ctl flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80 rounded-lg text-[var(--accent)] bg-[var(--surface-2)] border border-[var(--border)]"
        >
          Qualify <ArrowRight className="h-3 w-3" />
        </button>
      ),
    },
  ];

  /* ---- Render ---- */
  return (
    <div className="flex h-full flex-col space-y-5 p-6 lg:p-8">
      {/* ── Page Header ── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-violet-600">
            <ListChecks className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-tight txt">Qualification</h1>
            <p className="txt-muted mt-0.5 text-[13px] font-medium">Evaluate leads and identify high-value opportunities</p>
          </div>
        </div>
      </div>

      {/* ── Filters Bar ── */}
      <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
        <SearchInput placeholder="Search leads or companies..." value={search} onChange={(e) => setSearch(e.target.value)} containerClassName="flex-1 sm:max-w-xs" />
        <div className="flex flex-wrap gap-2">
          <FilterSelect options={SOURCE_OPTIONS} value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} />
          <FilterSelect options={STATUS_OPTIONS} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
        </div>
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-1">
          <button
            onClick={() => setViewMode('queue')}
            className={cn("rounded-md p-1.5 transition-colors", viewMode === 'queue' ? 'bg-[var(--surface)] shadow-sm' : 'text-[var(--muted)] hover:text-[var(--text)]')}
          >
            <ListOrdered className="h-4 w-4" />
          </button>
          <button
            onClick={() => setViewMode('table')}
            className={cn("rounded-md p-1.5 transition-colors", viewMode === 'table' ? 'bg-[var(--surface)] shadow-sm' : 'text-[var(--muted)] hover:text-[var(--text)]')}
          >
            <LayoutList className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* ── Data View ── */}
      <div className="min-h-[400px] flex-1">
        {viewMode === 'table' ? (
          <div className="surface bd overflow-hidden rounded-2xl border">
            <DataTable<QualLead>
              columns={columns}
              data={filtered}
              rowKey={(row) => row.id}
              sortKey={sortKey}
              sortDirection={sortDir}
              onSort={handleSort}
              onRowClick={handleRowClick}
              emptyMessage="No leads awaiting qualification"
            />
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
             {filtered.map(lead => (
               <div 
                 key={lead.id} 
                 onClick={() => handleRowClick(lead)}
                 className="surface bd flex flex-col gap-4 rounded-2xl border p-5 transition-all hover:shadow-md hover:border-[var(--accent)] cursor-pointer relative overflow-hidden"
               >
                 {/* Priority Accent Bar */}
                 <div className={cn("absolute left-0 top-0 bottom-0 w-1.5", lead.priority === 'High' ? 'bg-rose-500' : lead.priority === 'Medium' ? 'bg-amber-500' : 'bg-[var(--border)]')} />
                 
                 <div className="flex items-start justify-between pl-2">
                   <div>
                     <h3 className="txt text-[15px] font-bold leading-tight">{lead.leadName}</h3>
                     <p className="txt-muted text-[12.5px] mt-0.5 flex items-center gap-1.5">
                       <UserCheck className="h-3.5 w-3.5" /> {lead.company}
                     </p>
                   </div>
                   <div className="flex flex-col items-end gap-1.5">
                     <span className={cn("text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full", lead.priority === 'High' ? 'bg-rose-500/10 text-rose-500' : lead.priority === 'Medium' ? 'bg-amber-500/10 text-amber-600' : 'bg-[var(--surface-2)] text-[var(--muted)]')}>
                       {lead.priority} Priority
                     </span>
                     <span className="txt-faint text-[10px]">{lead.createdDate}</span>
                   </div>
                 </div>
                 
                 <div className="grid grid-cols-2 gap-3 pt-2 pl-2 border-t border-[var(--border)]">
                   <div className="flex flex-col">
                     <span className="txt-muted text-[10px] font-semibold uppercase tracking-wider mb-1">AI Score</span>
                     <span className={cn("font-display text-[22px] font-bold leading-none", lead.aiScore >= 80 ? 'text-emerald-500' : lead.aiScore >= 50 ? 'text-amber-500' : 'text-rose-500')}>
                       {lead.aiScore}
                     </span>
                   </div>
                   <div className="flex flex-col justify-center gap-1.5">
                      <div className="flex items-center gap-1.5">
                         <Target className="h-3.5 w-3.5 text-[var(--muted)]" />
                         <span className="txt text-[12px]">{lead.source}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                         <Users className="h-3.5 w-3.5 text-[var(--muted)]" />
                         <span className="txt text-[12px] truncate">{lead.owner}</span>
                      </div>
                   </div>
                 </div>

                 <div className="mt-auto pt-3 pl-2 flex items-center justify-between">
                    <StatusBadge label={lead.status} variant={lead.status === 'Qualified' ? 'success' : lead.status === 'In Review' ? 'accent' : lead.status === 'Disqualified' ? 'danger' : 'neutral'} />
                    <button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">
                      Begin Review <ArrowRight className="h-3 w-3" />
                    </button>
                 </div>
               </div>
             ))}
             {filtered.length === 0 && (
               <div className="col-span-full py-12 text-center text-[13px] font-medium txt-muted">No leads in queue.</div>
             )}
          </div>
        )}
      </div>
    </div>
  );
}
