'use client';

import { FileText, Globe, Plus } from 'lucide-react';

/**
 * Left "Sources" rail — in the real app this lists the selected project's
 * documents from the API. The template ships static demo data: replace
 * DEMO_SOURCES with your own fetch when wiring a backend.
 */
const DEMO_SOURCES = [
  { id: '1', title: 'Product overview.pdf', sourceType: 'file' },
  { id: '2', title: 'Q3 strategy notes.docx', sourceType: 'file' },
  { id: '3', title: 'company.com/about', sourceType: 'url' },
  { id: '4', title: 'Competitor analysis.pptx', sourceType: 'file' },
  { id: '5', title: 'blog.example.com/launch', sourceType: 'url' },
];

export default function SourcesRail() {
  return (
    <aside className="surface bd hidden w-[280px] shrink-0 flex-col overflow-y-auto border-r lg:flex">
      <div className="flex items-center justify-between p-4 pb-2">
        <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">Sources</span>
        <span className="ctl txt-muted rounded-full px-1.5 py-0.5 text-[10px]">{DEMO_SOURCES.length}</span>
      </div>

      <div className="flex-1 space-y-0.5 px-2.5">
        {DEMO_SOURCES.map((doc) => (
          <div
            key={doc.id}
            className="txt-muted flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[12px]"
            title={doc.title}
          >
            {doc.sourceType === 'url'
              ? <Globe className="txt-faint h-4 w-4 shrink-0" />
              : <FileText className="txt-faint h-4 w-4 shrink-0" />}
            <span className="flex-1 truncate">{doc.title}</span>
          </div>
        ))}
      </div>

      <div className="bd txt-faint border-t px-4 py-2 text-[10.5px] leading-snug">
        Attached documents feed this tool.
      </div>
      <div className="p-3 pt-2">
        <button className="ctl flex w-full items-center justify-center gap-2 py-2.5 text-[12.5px] font-semibold transition hover:opacity-80">
          <Plus className="h-4 w-4" /> Add source
        </button>
      </div>
    </aside>
  );
}
