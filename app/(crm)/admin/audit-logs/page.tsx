'use client';

import { useState, useMemo, useCallback } from 'react';
import { ScrollText, Download, Filter } from 'lucide-react';
import DataTable, { type ColumnDef, type SortDirection } from '@/components/crm/tables/DataTable';
import SearchInput from '@/components/crm/forms/SearchInput';
import StatusBadge from '@/components/crm/shared/StatusBadge';

interface AuditLog {
  id: string;
  user: string;
  action: string;
  module: string;
  timestamp: string;
  ipAddress: string;
  status: 'Success' | 'Failed' | 'Warning';
}

const INITIAL_DATA: AuditLog[] = [
  { id: '1', user: 'Mike Johnson', action: 'Login', module: 'Auth', timestamp: '2026-07-09 10:15:00', ipAddress: '192.168.1.105', status: 'Success' },
  { id: '2', user: 'System', action: 'Data Sync', module: 'Integrations', timestamp: '2026-07-09 10:00:00', ipAddress: 'Internal', status: 'Success' },
  { id: '3', user: 'Unknown', action: 'Failed Login', module: 'Auth', timestamp: '2026-07-09 09:45:12', ipAddress: '203.0.113.45', status: 'Failed' },
  { id: '4', user: 'Sarah Chen', action: 'Exported Leads', module: 'Leads', timestamp: '2026-07-09 09:30:00', ipAddress: '192.168.1.210', status: 'Success' },
  { id: '5', user: 'Admin', action: 'Modified Role', module: 'Security', timestamp: '2026-07-09 09:15:00', ipAddress: '10.0.0.5', status: 'Warning' },
];

export default function AdminAuditLogsPage() {
  const [data] = useState<AuditLog[]>(INITIAL_DATA);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);

  const filtered = useMemo(() => {
    let rows = data;
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(r => r.user.toLowerCase().includes(q) || r.action.toLowerCase().includes(q));
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

  const columns: ColumnDef<AuditLog>[] = [
    { key: 'timestamp', label: 'Timestamp', sortable: true, render: row => <span className="txt-muted text-[12px] font-mono">{row.timestamp}</span> },
    { key: 'user', label: 'User', sortable: true, render: row => <span className="txt text-[12.5px] font-semibold">{row.user}</span> },
    { key: 'action', label: 'Action', sortable: true, render: row => <span className="txt text-[12.5px]">{row.action}</span> },
    { key: 'module', label: 'Module', sortable: true, hideBelow: 'md', render: row => <span className="txt-muted text-[12.5px]">{row.module}</span> },
    { key: 'ipAddress', label: 'IP Address', hideBelow: 'lg', render: row => <span className="txt-faint text-[12px] font-mono">{row.ipAddress}</span> },
    { key: 'status', label: 'Status', sortable: true, render: row => <StatusBadge label={row.status} variant={row.status === 'Success' ? 'success' : row.status === 'Failed' ? 'danger' : 'warning'} /> },
  ];

  return (
    <div className="flex h-full flex-col space-y-5 p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-gray-500 to-slate-600">
            <ScrollText className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Audit Logs</h1>
            <p className="txt-muted mt-0.5 text-[13px]">System activity tracking and compliance.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
            <Filter className="h-4 w-4" /> Filter
          </button>
          <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
            <Download className="h-4 w-4" /> Export CSV
          </button>
        </div>
      </div>

      <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
        <SearchInput placeholder="Search by user or action..." value={search} onChange={e => setSearch(e.target.value)} containerClassName="flex-1 max-w-sm" />
      </div>

      <div className="surface bd overflow-hidden rounded-2xl border flex-1">
        <DataTable columns={columns} data={filtered} rowKey={row => row.id} sortKey={sortKey} sortDirection={sortDir} onSort={handleSort} onRowClick={() => {}} />
      </div>
    </div>
  );
}
