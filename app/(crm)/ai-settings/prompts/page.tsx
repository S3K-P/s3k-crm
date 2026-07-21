'use client';

import { useState } from 'react';
import { MessageSquareCode, Play, Copy, Pencil, Beaker } from 'lucide-react';
import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SectionHeader from '@/components/crm/shared/SectionHeader';

interface Prompt {
  id: string;
  name: string;
  category: string;
  version: string;
  lastUpdated: string;
}

const PROMPTS: Prompt[] = [
  { id: '1', name: 'Generate Executive Summary', category: 'Accounts', version: 'v2.1', lastUpdated: '2 days ago' },
  { id: '2', name: 'Draft Cold Outreach', category: 'Email AI', version: 'v4.0', lastUpdated: '1 week ago' },
  { id: '3', name: 'Extract Meeting Action Items', category: 'Meeting AI', version: 'v1.5', lastUpdated: '3 hours ago' },
  { id: '4', name: 'Qualify BANT Criteria', category: 'Leads', version: 'v3.2', lastUpdated: '1 month ago' },
  { id: '5', name: 'Analyze Deal Risk', category: 'Opportunities', version: 'v1.0', lastUpdated: 'Yesterday' },
];

export default function AIPromptsPage() {
  const [data] = useState(PROMPTS);

  const columns: ColumnDef<Prompt>[] = [
    { key: 'name', label: 'Prompt Name', render: row => <span className="txt text-[13px] font-semibold">{row.name}</span> },
    { key: 'category', label: 'Category', render: row => <span className="txt-muted text-[12px]">{row.category}</span> },
    { key: 'version', label: 'Version', render: row => <span className="text-[11px] font-mono bg-[var(--surface-2)] border border-[var(--border)] px-1.5 py-0.5 rounded">{row.version}</span> },
    { key: 'lastUpdated', label: 'Last Updated', render: row => <span className="txt-muted text-[12px]">{row.lastUpdated}</span> },
    {
      key: 'actions', label: '', align: 'right',
      render: () => (
        <div className="flex justify-end gap-2">
          <button className="p-1.5 rounded hover:bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--text)] transition-colors"><Pencil className="h-3.5 w-3.5" /></button>
          <button className="p-1.5 rounded hover:bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--text)] transition-colors"><Copy className="h-3.5 w-3.5" /></button>
          <button className="p-1.5 rounded hover:bg-[var(--surface-2)] text-[var(--muted)] hover:text-indigo-500 transition-colors"><Play className="h-3.5 w-3.5" /></button>
        </div>
      )
    }
  ];

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <MessageSquareCode className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Prompt Library</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Manage, version, and test the system prompts driving your AI features.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            New Prompt
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_350px] gap-6 flex-1 min-h-0">
        <div className="surface bd overflow-hidden rounded-2xl border flex flex-col h-full">
           <DataTable columns={columns} data={data} rowKey={r => r.id} />
        </div>

        <div className="surface bd rounded-2xl border p-5 flex flex-col h-full">
           <SectionHeader title="AI Playground" />
           <p className="txt-muted text-[12px] mt-2 mb-4">Test prompt outputs before deploying them to production.</p>
           
           <div className="flex-1 flex flex-col gap-4">
             <div>
               <label className="text-[11px] font-bold uppercase tracking-wider txt-muted mb-1.5 block">Select Prompt</label>
               <select className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg p-2 text-[13px] outline-none">
                 <option>Generate Executive Summary</option>
                 <option>Draft Cold Outreach</option>
               </select>
             </div>
             
             <div>
               <label className="text-[11px] font-bold uppercase tracking-wider txt-muted mb-1.5 block">Sample Variables (JSON)</label>
               <textarea className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg p-3 text-[12px] font-mono h-24 outline-none resize-none" defaultValue={"{ \"companyName\": \"Acme Corp\", \"dealValue\": \"$50,000\" }"} />
             </div>

             <button className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-white font-semibold text-[13px] bg-indigo-500 hover:bg-indigo-600 transition-colors mt-auto">
               <Play className="h-4 w-4" /> Run Test
             </button>
             
             <div className="h-32 border border-dashed border-[var(--border)] rounded-lg bg-[var(--surface-2)] flex items-center justify-center p-4">
               <span className="text-[12px] txt-muted text-center">Output will appear here.</span>
             </div>
           </div>
        </div>
      </div>
    </div>
  );
}
