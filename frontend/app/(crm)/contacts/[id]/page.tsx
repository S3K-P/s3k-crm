'use client';

import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, User, Building2, Phone, Mail, FileText, Target, Calendar, ArrowRight, Video, Briefcase, Plus } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import AIPanel, { type AIPanelData } from '@/components/crm/ai/AIPanel';
import ActivityItem from '@/components/crm/cards/ActivityItem';

/* ============================================================
   MOCK DATA
   ============================================================ */
const MOCK_CONTACT = {
  id: '1',
  firstName: 'Sarah',
  lastName: 'Chen',
  jobTitle: 'Chief Marketing Officer',
  department: 'Marketing',
  account: 'Acme Corp',
  email: 'sarah.c@acme.com',
  phone: '+1 555-0101',
  mobile: '+1 555-0102',
  owner: 'Mike Johnson',
  reportingManager: 'David Smith',
  status: 'Active',
  preferredCommunication: 'Email',
  linkedInUrl: 'linkedin.com/in/sarahchen',
  country: 'USA',
  state: 'CA',
  city: 'San Francisco',
  postalCode: '94105',
  address: '123 Tech Blvd',
  notes: 'Key decision maker for marketing suite. Prefers concise, data-driven proposals.',
};

const MOCK_AI_DATA: AIPanelData = {
  engagementScore: 95,
  relationshipStrength: 'Strong',
  preferredCommunicationStyle: 'Analytical and direct. Avoids fluff. Prefers email updates over spontaneous calls.',
  recentSentiment: 'Positive',
  suggestedNextAction: 'Share the recent Q3 marketing ROI case study.',
  contactSummary: 'Sarah is a champion for our product within Acme Corp. She has high engagement with our content and is currently evaluating an expansion to the entire marketing department.',
};

const MOCK_ACTIVITIES = [
  { id: '1', icon: Mail, iconGradient: 'from-sky-500 to-blue-600', title: 'Email Opened', detail: 'Subject: "Q3 Roadmap Preview"', timestamp: '2 hours ago' },
  { id: '2', icon: Video, iconGradient: 'from-emerald-500 to-green-600', title: 'Attended Webinar', detail: '"Future of AI in Marketing"', timestamp: '1 week ago' },
  { id: '3', icon: FileText, iconGradient: 'from-amber-500 to-orange-500', title: 'Downloaded Case Study', detail: '"Enterprise ROI 2026"', timestamp: '2 weeks ago' },
];

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function ContactDetailsPage() {
  const router = useRouter();
  const { id } = useParams();
  
  // Real app would fetch contact by id here.
  const contact = MOCK_CONTACT;

  const tabs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Contact Details" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Email</p><p className="txt text-[13.5px] mt-1"><a href={`mailto:${contact.email}`} className="hover:text-[var(--accent)]">{contact.email}</a></p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Phone (Work)</p><p className="txt text-[13.5px] mt-1">{contact.phone}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Mobile</p><p className="txt text-[13.5px] mt-1">{contact.mobile}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">LinkedIn</p><p className="txt text-[13.5px] mt-1"><a href={`https://${contact.linkedInUrl}`} className="hover:text-[var(--accent)]">{contact.linkedInUrl}</a></p></div>
              </div>
            </div>
            
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Company & CRM" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Department</p><p className="txt text-[13.5px] mt-1">{contact.department}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Reporting Manager</p><p className="txt text-[13.5px] mt-1">{contact.reportingManager || 'N/A'}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Contact Owner</p><p className="txt text-[13.5px] mt-1">{contact.owner}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Preferred Comms</p><p className="txt text-[13.5px] mt-1">{contact.preferredCommunication}</p></div>
              </div>
            </div>
          </div>
          
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Address" />
            <div className="grid gap-6 md:grid-cols-3 pt-2">
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Street</p><p className="txt text-[13.5px] mt-1">{contact.address}</p></div>
              <div><p className="txt-muted text-[12px] font-semibold uppercase">City, State</p><p className="txt text-[13.5px] mt-1">{contact.city}, {contact.state}</p></div>
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Country / Postal</p><p className="txt text-[13.5px] mt-1">{contact.country} {contact.postalCode}</p></div>
            </div>
          </div>

          {/* Related Records Widgets */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Associated Account" />
              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-2)] text-[12px] font-bold text-[var(--accent)]">
                      <Building2 className="h-5 w-5" />
                    </div>
                    <div><p className="txt text-[14px] font-semibold">{contact.account}</p><p className="txt-faint text-[12px]">Technology • Enterprise</p></div>
                  </div>
                  <button className="text-[var(--accent)] hover:opacity-80"><ArrowRight className="h-4 w-4" /></button>
                </div>
              </div>
            </div>

            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Open Opportunities" action={<button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">View all <ArrowRight className="h-3 w-3" /></button>} />
              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div><p className="txt text-[13px] font-semibold">Enterprise Expansion - Q3</p><p className="txt-faint text-[11px]">Role: Decision Maker</p></div>
                  <span className="font-display txt text-[14px] font-bold">$150,000</span>
                </div>
              </div>
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
      ) 
    },
    { id: 'meetings', label: 'Meetings', content: <div className="p-4 text-[13px] txt-faint">No upcoming meetings.</div> },
    { id: 'opportunities', label: 'Opportunities', content: <div className="p-4 text-[13px] txt-faint">Opportunities list coming soon.</div> },
    { id: 'emails', label: 'Emails', content: <div className="p-4 text-[13px] txt-faint">No recent emails.</div> },
    { id: 'notes', label: 'Notes', content: <div className="p-4 text-[13px] txt-faint">{contact.notes}</div> },
    { id: 'files', label: 'Files', content: <div className="p-4 text-[13px] txt-faint">No files uploaded.</div> },
    { id: 'timeline', label: 'Timeline', content: <div className="p-4 text-[13px] txt-faint">Timeline view coming soon.</div> },
  ];

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      
      {/* ── Page Header ── */}
      <div className="flex flex-col gap-4">
        <button onClick={() => router.push('/contacts')} className="txt-muted hover:txt flex w-fit items-center gap-1 text-[13px] font-medium transition-colors">
          <ArrowLeft className="h-4 w-4" /> Back to Contacts
        </button>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-emerald-500 to-green-600 shadow-sm">
              <span className="font-display text-[22px] font-bold text-white">{contact.firstName[0]}{contact.lastName[0]}</span>
            </div>
            <div className="mt-1">
              <div className="flex items-center gap-3">
                <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
                  {contact.firstName} {contact.lastName}
                </h1>
                <StatusBadge label={contact.status} variant="success" />
              </div>
              <div className="txt-muted mt-1.5 flex items-center gap-3 text-[13px] font-medium">
                <span>{contact.jobTitle}</span>
                <span className="flex items-center gap-1.5 border-l border-[var(--border)] pl-3"><Building2 className="h-4 w-4" /> {contact.account}</span>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Calendar className="h-4 w-4" /> Schedule
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Mail className="h-4 w-4" /> Email
            </button>
            <button
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90 hover:shadow-md"
              style={{ background: 'var(--accent)' }}
            >
              <Plus className="h-4 w-4" /> Opportunity
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
