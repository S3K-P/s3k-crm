'use client';

import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Target, Building2, Phone, Mail, FileText, Calendar, ArrowRight, CheckCircle2, ChevronRight, Activity, Users } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import AIPanel, { type AIPanelData } from '@/components/crm/ai/AIPanel';
import AICommandBar from '@/components/crm/ai/AICommandBar';
import ActivityItem from '@/components/crm/cards/ActivityItem';

/* ============================================================
   MOCK DATA
   ============================================================ */
const MOCK_OPP = {
  id: '1',
  name: 'Enterprise Expansion - Q3',
  account: 'Acme Corp',
  primaryContact: 'Sarah Chen',
  owner: 'Mike Johnson',
  stage: 'Negotiation',
  dealValue: '$150,000',
  winProbability: 85,
  expectedCloseDate: '2026-09-30',
  forecastCategory: 'Commit',
  products: 'Enterprise Suite, Advanced Analytics',
  competitor: 'Competitor A',
};

const MOCK_AI_DATA: AIPanelData = {
  healthScore: 92,
  winProbability: 85,
  revenuePotential: '$150,000',
  riskLevel: 'Low',
  missingInformation: 'Procurement contact details are missing.',
  stakeholdersToEngage: 'Need to loop in the CFO for final financial sign-off.',
  nextBestAction: 'Send the final contract draft and schedule a review call with procurement.',
  executiveSummary: 'This deal is progressing smoothly through Negotiation. Legal has minor redlines which are being addressed. High probability of closing this month.',
};

const MOCK_ACTIVITIES = [
  { id: '1', icon: FileText, iconGradient: 'from-amber-500 to-orange-500', title: 'Contract Revised', detail: 'Uploaded version 2 of the MSA.', timestamp: '2 hours ago' },
  { id: '2', icon: Phone, iconGradient: 'from-emerald-500 to-green-600', title: 'Negotiation Call', detail: 'Discussed pricing tiers with Sarah Chen.', timestamp: '1 day ago' },
  { id: '3', icon: Activity, iconGradient: 'from-violet-500 to-indigo-500', title: 'Stage Updated', detail: 'Moved from Proposal to Negotiation.', timestamp: '3 days ago' },
];

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function OpportunityDetailsPage() {
  const router = useRouter();
  const { id } = useParams();
  
  // Real app would fetch opp by id here.
  const opp = MOCK_OPP;

  const tabs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Deal Information" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Expected Close Date</p><p className="txt text-[13.5px] mt-1">{opp.expectedCloseDate}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Forecast Category</p><p className="txt text-[13.5px] mt-1">{opp.forecastCategory}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Products</p><p className="txt text-[13.5px] mt-1">{opp.products}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Competitor</p><p className="txt text-[13.5px] mt-1">{opp.competitor}</p></div>
              </div>
            </div>
            
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Related Account" />
              <div className="flex flex-col gap-4 pt-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-2)] text-[12px] font-bold text-[var(--accent)]">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div><p className="txt text-[14px] font-semibold">{opp.account}</p><p className="txt-faint text-[12px]">Technology • Enterprise</p></div>
                </div>
                <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
                  <span className="txt text-[12.5px] font-semibold">Primary Contact: {opp.primaryContact}</span>
                  <button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">View Account <ArrowRight className="h-3 w-3" /></button>
                </div>
              </div>
            </div>
          </div>

          {/* Related Records Widgets */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Key Contacts" action={<button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">View all <ArrowRight className="h-3 w-3" /></button>} />
              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--surface-2)] text-[11px] font-bold text-[var(--accent)]">SC</div>
                    <div><p className="txt text-[13px] font-semibold">{opp.primaryContact}</p><p className="txt-faint text-[11px]">CMO (Decision Maker)</p></div>
                  </div>
                  <Mail className="h-4 w-4 text-[var(--faint)]" />
                </div>
              </div>
            </div>
            
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Attachments" action={<button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">View all <ArrowRight className="h-3 w-3" /></button>} />
              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-amber-500" />
                    <div><p className="txt text-[13px] font-semibold">MSA_v2.pdf</p><p className="txt-faint text-[11px]">Uploaded 2 hours ago</p></div>
                  </div>
                </div>
                <div className="flex items-center justify-between pb-1">
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-rose-500" />
                    <div><p className="txt text-[13px] font-semibold">Proposal_Final.pdf</p><p className="txt-faint text-[11px]">Uploaded 1 week ago</p></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      ),
    },
    { 
      id: 'timeline', 
      label: 'Timeline', 
      content: (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Deal Timeline" />
          <div className="pt-2">
            {MOCK_ACTIVITIES.map((activity, i) => (
              <ActivityItem key={activity.id} activity={activity} showConnector={i < MOCK_ACTIVITIES.length - 1} />
            ))}
          </div>
        </div>
      ) 
    },
    { id: 'activities', label: 'Activities', content: <div className="p-4 text-[13px] txt-faint">Activities view coming soon.</div> },
    { id: 'meetings', label: 'Meetings', content: <div className="p-4 text-[13px] txt-faint">No upcoming meetings.</div> },
    { id: 'contacts', label: 'Contacts', content: <div className="p-4 text-[13px] txt-faint">Contacts list coming soon.</div> },
    { id: 'notes', label: 'Notes', content: <div className="p-4 text-[13px] txt-faint">No notes added.</div> },
    { id: 'files', label: 'Files', content: <div className="p-4 text-[13px] txt-faint">Files list coming soon.</div> },
    { id: 'forecast', label: 'Forecast', content: <div className="p-4 text-[13px] txt-faint">Forecast breakdown coming soon.</div> },
  ];

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      
      {/* ── AI Command Bar ── */}
      <AICommandBar />

      {/* ── Page Header ── */}
      <div className="flex flex-col gap-4">
        <button onClick={() => router.push('/opportunities')} className="txt-muted hover:txt flex w-fit items-center gap-1 text-[13px] font-medium transition-colors">
          <ArrowLeft className="h-4 w-4" /> Back to Opportunities
        </button>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-indigo-500 to-violet-600 shadow-sm">
              <Target className="h-6 w-6 text-white" />
            </div>
            <div className="mt-1">
              <div className="flex items-center gap-3">
                <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
                  {opp.name}
                </h1>
                <span className="font-display txt text-[20px] font-bold text-[var(--accent)]">{opp.dealValue}</span>
              </div>
              <div className="txt-muted mt-1.5 flex items-center gap-2 text-[13px] font-medium">
                <span className="flex items-center gap-1"><Building2 className="h-4 w-4" /> {opp.account}</span>
                <ChevronRight className="h-3 w-3 text-[var(--border)]" />
                <StatusBadge label={opp.stage} variant="accent" />
                <span className="border-l border-[var(--border)] pl-2 ml-1">Owner: {opp.owner}</span>
              </div>
            </div>
          </div>
          
          <div className="flex flex-wrap items-center gap-2">
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Calendar className="h-4 w-4" /> Meeting
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Phone className="h-4 w-4" /> Log Call
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <FileText className="h-4 w-4" /> Proposal
            </button>
            <button
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90 hover:shadow-md"
              style={{ background: 'var(--accent)' }}
            >
              <CheckCircle2 className="h-4 w-4" /> Update Stage
            </button>
          </div>
        </div>
      </div>

      {/* ── Content Area: Main + Sidebar ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        {/* Left: Main Tabs */}
        <div className="min-w-0">
           <Tabs tabs={tabs} defaultTab="overview" />
        </div>
        
        {/* Right: AI Panel Sidebar */}
        <div className="flex flex-col gap-6">
          <AIPanel data={MOCK_AI_DATA} />
        </div>
      </div>
    </div>
  );
}
