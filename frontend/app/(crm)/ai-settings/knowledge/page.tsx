'use client';

import { BookOpen, Database, RefreshCw, FileText, Globe } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';

const SOURCES = [
  { name: 'CRM Records', type: 'Database', count: '142,500 records', status: 'Synced', icon: Database },
  { name: 'Sales Playbooks', type: 'Documents', count: '24 PDFs', status: 'Synced', icon: FileText },
  { name: 'Company Website', type: 'Web Scraping', count: '340 pages', status: 'Indexing', icon: Globe },
  { name: 'Meeting Transcripts', type: 'Audio Data', count: '1,204 hours', status: 'Synced', icon: FileText },
];

export default function AIKnowledgeBasePage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <BookOpen className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Knowledge Base</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Manage the context window and vector database sources for your AI models.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            Add Data Source
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 surface bd rounded-2xl border p-5">
          <SectionHeader title="Active Data Sources" />
          <div className="mt-4 space-y-3">
             {SOURCES.map(source => (
               <div key={source.name} className="flex items-center justify-between p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                 <div className="flex items-center gap-4">
                   <div className="h-10 w-10 rounded-lg bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center">
                     <source.icon className="h-5 w-5 text-indigo-500" />
                   </div>
                   <div>
                     <h4 className="txt text-[14px] font-bold">{source.name}</h4>
                     <p className="txt-muted text-[12px] mt-0.5">{source.type} • {source.count}</p>
                   </div>
                 </div>
                 <div className="flex flex-col items-end gap-2">
                   <StatusBadge label={source.status} variant={source.status === 'Synced' ? 'success' : 'warning'} />
                   <button className="flex items-center gap-1 text-[11px] font-medium txt-muted hover:text-[var(--accent)] transition-colors">
                     <RefreshCw className="h-3 w-3" /> Sync Now
                   </button>
                 </div>
               </div>
             ))}
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5 flex flex-col">
          <SectionHeader title="Vector Database Sync" />
          
          <div className="mt-6 flex-1 flex flex-col items-center justify-center border border-dashed border-[var(--border)] rounded-xl bg-[var(--surface-2)] p-6 text-center">
            <RefreshCw className="h-8 w-8 text-[var(--accent)] mb-3 animate-spin-slow" />
            <h4 className="txt text-[14px] font-bold">Indexing in Progress</h4>
            <p className="txt-muted text-[12px] mt-1 leading-relaxed">Processing 340 pages from Company Website.</p>
            
            <div className="w-full mt-4 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
               <div className="h-full bg-[var(--accent)] w-[45%]" />
            </div>
            <p className="text-[11px] txt-faint mt-2">Estimated time remaining: 2m 14s</p>
          </div>
        </div>
      </div>
    </div>
  );
}
