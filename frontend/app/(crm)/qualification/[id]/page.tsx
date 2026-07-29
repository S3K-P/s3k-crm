'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, ArrowRight, UserCheck, Building2, Phone, Mail, FileText, Activity, MapPin, Sparkles, CheckSquare, Target, Repeat } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import AICommandBar from '@/components/crm/ai/AICommandBar';
import AIQualificationAssistant, { type AIQualificationAssistantData } from '@/components/crm/ai/AIQualificationAssistant';
import { cn } from '@/lib/utils';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';

/* ============================================================
   MOCK DATA
   ============================================================ */
const MOCK_LEAD = {
  id: '1',
  name: 'Alice Johnson',
  company: 'TechCorp Inc.',
  title: 'VP of Engineering',
  email: 'alice@techcorp.com',
  phone: '+1 (555) 123-4567',
  location: 'San Francisco, CA',
  source: 'Webinar - Q3 DevOps',
  status: 'In Review',
  createdDate: '2026-07-08',
  owner: 'Mike Johnson'
};

const MOCK_AI_DATA: AIQualificationAssistantData = {
  qualificationScore: 85,
  buyingIntent: 'High',
  probabilityToConvert: '78%',
  missingInformation: ['Exact budget numbers', 'Procurement timeline specifics'],
  suggestedDiscoveryQuestions: [
    'How does your team currently handle infrastructure scaling?',
    'Who else is involved in the technical evaluation process?',
    'What happens if you do not implement a new solution this quarter?'
  ],
  recommendedNextActions: [
    'Schedule a technical deep-dive.',
    'Send the DevOps case study.'
  ],
  executiveSummary: 'Alice showed high engagement during the DevOps webinar. Her title suggests strong technical authority, but we need to confirm economic buyers and timeline.'
};

type Framework = 'BANT' | 'MEDDICC' | 'CHAMP';

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function QualificationWorkspacePage() {
  const router = useRouter();
  const { id } = useParams();
  
  const lead = MOCK_LEAD;
  const [framework, setFramework] = useState<Framework>('BANT');
  const [convertOpen, setConvertOpen] = useState(false);

  // Simple mock checklist state
  const [checklist, setChecklist] = useState<Record<string, boolean>>({
    'Budget Confirmed': false,
    'Authority Verified': true,
    'Need Established': true,
    'Timeline Defined': false,
  });

  const toggleCheck = (key: string) => {
    setChecklist(prev => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      
      {/* ── AI Command Bar ── */}
      <AICommandBar />

      {/* ── Page Header ── */}
      <div className="flex flex-col gap-4">
        <button onClick={() => router.push('/qualification')} className="txt-muted hover:txt flex w-fit items-center gap-1 text-[13px] font-medium transition-colors">
          <ArrowLeft className="h-4 w-4" /> Back to Queue
        </button>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-indigo-500 to-violet-600 shadow-sm">
              <UserCheck className="h-6 w-6 text-white" />
            </div>
            <div className="mt-1">
              <div className="flex items-center gap-3">
                <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
                  {lead.name}
                </h1>
                <StatusBadge label={lead.status} variant="accent" />
              </div>
              <div className="txt-muted mt-1.5 flex items-center gap-2 text-[13px] font-medium">
                <span className="flex items-center gap-1"><Building2 className="h-4 w-4" /> {lead.company}</span>
                <span className="border-l border-[var(--border)] pl-2 ml-1 flex items-center gap-1"><Target className="h-4 w-4" /> {lead.source}</span>
              </div>
            </div>
          </div>
          
          <div className="flex flex-wrap items-center gap-2 mt-2 sm:mt-0">
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              Assign Owner
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              Disqualify
            </button>
            <button
              onClick={() => setConvertOpen(true)}
              className="flex items-center gap-2 rounded-lg px-6 py-2 text-[13px] font-bold text-white shadow-sm transition hover:opacity-90 hover:shadow-md"
              style={{ background: 'var(--accent)' }}
            >
              <Repeat className="h-4 w-4" /> Convert Lead
            </button>
          </div>
        </div>
      </div>

      {/* ── Content Area ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        
        {/* Left: Main Workspace */}
        <div className="flex flex-col gap-6">
          
          {/* Summary Cards */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Contact Summary" />
              <div className="space-y-3 pt-2">
                <div className="flex items-center gap-3">
                  <Mail className="h-4 w-4 text-[var(--muted)]" />
                  <span className="txt text-[13.5px] font-medium">{lead.email}</span>
                </div>
                <div className="flex items-center gap-3">
                  <Phone className="h-4 w-4 text-[var(--muted)]" />
                  <span className="txt text-[13.5px] font-medium">{lead.phone}</span>
                </div>
                <div className="flex items-center gap-3">
                  <UserCheck className="h-4 w-4 text-[var(--muted)]" />
                  <span className="txt text-[13.5px] font-medium">{lead.title}</span>
                </div>
                <div className="flex items-center gap-3">
                  <MapPin className="h-4 w-4 text-[var(--muted)]" />
                  <span className="txt text-[13.5px] font-medium">{lead.location}</span>
                </div>
              </div>
            </div>

            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Lead Routing" />
              <div className="space-y-4 pt-2">
                <div>
                  <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider mb-1">Assigned Owner</p>
                  <p className="txt text-[13.5px] font-semibold">{lead.owner}</p>
                </div>
                <div>
                  <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider mb-1">Created Date</p>
                  <p className="txt text-[13.5px]">{lead.createdDate}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Qualification Framework UI */}
          <div className="surface bd rounded-2xl border overflow-hidden">
            <div className="bg-[var(--surface-2)] border-b border-[var(--border)] p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="font-display txt text-[18px] font-bold">Qualification Framework</h3>
                <p className="txt-muted mt-0.5 text-[12.5px]">Evaluate using structured sales methodologies.</p>
              </div>
              <div className="flex bg-[var(--surface)] border border-[var(--border)] rounded-lg p-1 w-fit">
                {(['BANT', 'MEDDICC', 'CHAMP'] as Framework[]).map(fw => (
                  <button
                    key={fw}
                    onClick={() => setFramework(fw)}
                    className={cn(
                      "px-4 py-1.5 text-[12px] font-bold rounded-md transition-colors",
                      framework === fw ? "bg-[var(--surface-2)] text-[var(--text)] shadow-sm" : "text-[var(--muted)] hover:text-[var(--text)]"
                    )}
                  >
                    {fw}
                  </button>
                ))}
              </div>
            </div>

            <div className="p-5">
              {/* Dynamic Checklist based on framework (simplified for mock) */}
              <div className="grid sm:grid-cols-2 gap-4">
                {Object.keys(checklist).map(item => (
                  <div 
                    key={item} 
                    className={cn(
                      "flex items-start gap-3 p-4 rounded-xl border transition-colors cursor-pointer select-none",
                      checklist[item] ? "bg-emerald-500/5 border-emerald-500/20" : "bg-[var(--surface-2)] border-[var(--border)] hover:border-[var(--accent)]"
                    )}
                    onClick={() => toggleCheck(item)}
                  >
                    <div className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border", checklist[item] ? "bg-emerald-500 border-emerald-500 text-white" : "border-[var(--border)] bg-[var(--surface)] text-transparent")}>
                      <CheckSquare className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <p className={cn("text-[13.5px] font-semibold", checklist[item] ? "text-emerald-700 dark:text-emerald-400" : "txt")}>{item}</p>
                      <p className="txt-muted text-[11px] mt-0.5">Click to toggle status</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
        
        {/* Right: AI Panel Sidebar */}
        <div className="flex flex-col gap-6">
          <AIQualificationAssistant data={MOCK_AI_DATA} />
          
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Quick Actions" />
            <div className="flex flex-col gap-2 pt-2">
              <button className="ctl flex w-full items-center justify-between px-4 py-2.5 text-[12.5px] font-medium rounded-lg">
                Schedule Discovery Call <ArrowRight className="h-4 w-4" />
              </button>
              <button className="ctl flex w-full items-center justify-between px-4 py-2.5 text-[12.5px] font-medium rounded-lg">
                Request More Information <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Convert Dialog (Mock) ── */}
      <SlideDrawer
        open={convertOpen}
        onClose={() => setConvertOpen(false)}
        title="Convert Lead"
        subtitle="This action will promote the lead into active CRM records."
        width="max-w-md"
        footer={
          <>
            <button onClick={() => setConvertOpen(false)} className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80">Cancel</button>
            <button onClick={() => { setConvertOpen(false); router.push('/opportunities'); }} className="rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
              Confirm Conversion
            </button>
          </>
        }
      >
        <div className="space-y-6">
          <p className="txt text-[13px] leading-relaxed">
            Converting <strong className="font-bold">{lead.name}</strong> will create the following records in your CRM:
          </p>

          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-4 bg-[var(--surface-2)] p-4 rounded-xl border border-[var(--border)]">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--surface)] shadow-sm">
                <Building2 className="h-5 w-5 text-indigo-500" />
              </div>
              <div>
                <p className="txt-muted text-[11px] font-bold uppercase">New Account</p>
                <p className="txt text-[14px] font-bold mt-0.5">{lead.company}</p>
              </div>
            </div>

            <div className="flex items-center gap-4 bg-[var(--surface-2)] p-4 rounded-xl border border-[var(--border)]">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--surface)] shadow-sm">
                <UserCheck className="h-5 w-5 text-violet-500" />
              </div>
              <div>
                <p className="txt-muted text-[11px] font-bold uppercase">New Contact</p>
                <p className="txt text-[14px] font-bold mt-0.5">{lead.name}</p>
              </div>
            </div>

            <div className="flex items-center gap-4 bg-[var(--surface-2)] p-4 rounded-xl border border-[var(--border)]">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--surface)] shadow-sm">
                <Target className="h-5 w-5 text-emerald-500" />
              </div>
              <div>
                <p className="txt-muted text-[11px] font-bold uppercase">New Opportunity</p>
                <p className="txt text-[14px] font-bold mt-0.5">{lead.company} - New Business</p>
              </div>
            </div>
          </div>
        </div>
      </SlideDrawer>
    </div>
  );
}
