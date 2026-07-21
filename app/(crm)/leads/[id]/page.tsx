'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, User, Building2, Phone, Mail, FileText, ArrowRightLeft, Sparkles, CheckCircle2 } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import AIPanel, { type AIPanelData } from '@/components/crm/ai/AIPanel';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import ActivityItem from '@/components/crm/cards/ActivityItem';

/* ============================================================
   MOCK DATA
   ============================================================ */
const MOCK_LEAD = {
  id: '1',
  firstName: 'John',
  lastName: 'Doe',
  company: 'Acme Corp',
  title: 'Chief Marketing Officer',
  email: 'john@acme.com',
  phone: '+1 555-0101',
  source: 'Website',
  owner: 'Sarah Chen',
  status: 'Qualified',
  industry: 'Technology',
  website: 'acme.com',
  companySize: '100-500',
  priority: 'High',
  expectedDealSize: '$50,000',
  notes: 'Interested in Enterprise plan.',
};

const MOCK_AI_DATA: AIPanelData = {
  qualificationScore: 85,
  buyingIntent: 'High',
  nextBestAction: 'Schedule a product demo focusing on enterprise security features.',
  suggestedFollowUp: 'Send an email introducing the dedicated account manager and sharing the security whitepaper.',
  riskLevel: 'Low',
  executiveSummary: 'John has shown consistent engagement with our pricing page and recently attended the Q3 roadmap webinar. High probability of closing if we can address their data residency requirements.',
};

const MOCK_ACTIVITIES = [
  { id: '1', icon: Phone, iconGradient: 'from-emerald-500 to-green-600', title: 'Discovery Call completed', detail: 'Discussed initial requirements and timeline.', timestamp: '2 hours ago' },
  { id: '2', icon: Mail, iconGradient: 'from-sky-500 to-blue-600', title: 'Email sent', detail: 'Follow-up with pricing details.', timestamp: 'Yesterday' },
  { id: '3', icon: FileText, iconGradient: 'from-amber-500 to-orange-500', title: 'Downloaded Whitepaper', detail: '"Enterprise Security in 2026"', timestamp: '3 days ago' },
];

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function LeadDetailsPage() {
  const router = useRouter();
  const { id } = useParams();
  
  // Real app would fetch lead by id here. Using MOCK_LEAD for now.
  const lead = MOCK_LEAD;

  const [convertModalOpen, setConvertModalOpen] = useState(false);

  const tabs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Contact Information" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Email</p><p className="txt text-[13.5px] mt-1">{lead.email}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Phone</p><p className="txt text-[13.5px] mt-1">{lead.phone}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Title</p><p className="txt text-[13.5px] mt-1">{lead.title}</p></div>
              </div>
            </div>
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Company Information" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Company</p><p className="txt text-[13.5px] mt-1">{lead.company}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Industry</p><p className="txt text-[13.5px] mt-1">{lead.industry}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Website</p><p className="txt text-[13.5px] mt-1">{lead.website}</p></div>
              </div>
            </div>
          </div>
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Sales Information" />
            <div className="grid gap-6 md:grid-cols-3 pt-2">
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Expected Deal Size</p><p className="txt text-[13.5px] mt-1">{lead.expectedDealSize}</p></div>
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Priority</p><p className="txt mt-1"><StatusBadge label={lead.priority} variant={lead.priority === 'High' ? 'danger' : lead.priority === 'Medium' ? 'warning' : 'neutral'} /></p></div>
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Lead Source</p><p className="txt text-[13.5px] mt-1">{lead.source}</p></div>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'activities',
      label: 'Activities',
      content: (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Recent Activities" />
          <div className="pt-2">
            {MOCK_ACTIVITIES.map((activity, i) => (
              <ActivityItem key={activity.id} activity={activity} showConnector={i < MOCK_ACTIVITIES.length - 1} />
            ))}
          </div>
        </div>
      ),
    },
    { id: 'meetings', label: 'Meetings', content: <div className="p-4 text-[13px] txt-faint">No meetings scheduled.</div> },
    { id: 'emails', label: 'Emails', content: <div className="p-4 text-[13px] txt-faint">No emails synced.</div> },
    { id: 'notes', label: 'Notes', content: <div className="p-4 text-[13px] txt-faint">{lead.notes}</div> },
    { id: 'attachments', label: 'Attachments', content: <div className="p-4 text-[13px] txt-faint">No attachments.</div> },
    { id: 'timeline', label: 'Timeline', content: <div className="p-4 text-[13px] txt-faint">Timeline view coming soon.</div> },
  ];

  return (
    <>
      <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
        
        {/* ── Page Header ── */}
        <div className="flex flex-col gap-4">
          <button onClick={() => router.push('/leads')} className="txt-muted hover:txt flex w-fit items-center gap-1 text-[13px] font-medium transition-colors">
            <ArrowLeft className="h-4 w-4" /> Back to Leads
          </button>
          
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-violet-600 to-indigo-500 shadow-sm">
                <span className="font-display text-[22px] font-bold text-white">{lead.firstName[0]}{lead.lastName[0]}</span>
              </div>
              <div className="mt-1">
                <div className="flex items-center gap-3">
                  <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
                    {lead.firstName} {lead.lastName}
                  </h1>
                  <StatusBadge label={lead.status} variant="success" />
                </div>
                <div className="txt-muted mt-1.5 flex items-center gap-3 text-[13px] font-medium">
                  <span className="flex items-center gap-1.5"><Building2 className="h-4 w-4" /> {lead.company}</span>
                  <span className="flex items-center gap-1.5"><User className="h-4 w-4" /> Owner: {lead.owner}</span>
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setConvertModalOpen(true)}
                className="flex items-center gap-2 rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90 hover:shadow-md"
                style={{ background: 'var(--accent)' }}
              >
                <ArrowRightLeft className="h-4 w-4" /> Convert Lead
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

      {/* ── Convert Lead Modal ── */}
      <SlideDrawer
        open={convertModalOpen}
        onClose={() => setConvertModalOpen(false)}
        title="Convert Lead"
        subtitle="This lead is ready to be converted into an active customer or opportunity."
        width="max-w-md"
        footer={
          <>
            <button onClick={() => setConvertModalOpen(false)} className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80">Cancel</button>
            <button onClick={() => setConvertModalOpen(false)} className="rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
              Confirm Conversion
            </button>
          </>
        }
      >
        <div className="space-y-6">
           <div className="surface-2 rounded-xl border border-[var(--border)] p-4 text-[13px] leading-relaxed txt-muted">
             Converting this lead will create the following records in your CRM. You can review and edit them later.
           </div>

           <div className="space-y-4">
             <div className="flex items-start gap-3">
               <div className="mt-0.5 text-emerald-500"><CheckCircle2 className="h-5 w-5" /></div>
               <div>
                 <h4 className="txt font-bold text-[14px]">New Account</h4>
                 <p className="txt-muted text-[13px] mt-0.5">{lead.company}</p>
               </div>
             </div>
             
             <div className="flex items-start gap-3">
               <div className="mt-0.5 text-emerald-500"><CheckCircle2 className="h-5 w-5" /></div>
               <div>
                 <h4 className="txt font-bold text-[14px]">New Contact</h4>
                 <p className="txt-muted text-[13px] mt-0.5">{lead.firstName} {lead.lastName}</p>
               </div>
             </div>

             <div className="flex items-start gap-3">
               <div className="mt-0.5 text-emerald-500"><CheckCircle2 className="h-5 w-5" /></div>
               <div>
                 <h4 className="txt font-bold text-[14px]">New Opportunity</h4>
                 <p className="txt-muted text-[13px] mt-0.5">{lead.company} - {lead.expectedDealSize} Deal</p>
               </div>
             </div>
           </div>
        </div>
      </SlideDrawer>
    </>
  );
}
