'use client';

import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Building2, Phone, Mail, FileText, Target, Users, Calendar, ArrowRight } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import AIPanel, { type AIPanelData } from '@/components/crm/ai/AIPanel';
import ActivityItem from '@/components/crm/cards/ActivityItem';

/* ============================================================
   MOCK DATA
   ============================================================ */
const MOCK_ACCOUNT = {
  id: '1',
  name: 'Acme Corp',
  industry: 'Technology',
  website: 'acme.com',
  owner: 'Mike Johnson',
  status: 'Active',
  companySize: '100-500',
  annualRevenue: '$50M+',
  country: 'USA',
  state: 'CA',
  city: 'San Francisco',
  postalCode: '94105',
  address: '123 Tech Blvd',
  source: 'Direct',
  description: 'Key enterprise account looking to expand usage across departments.',
};

const MOCK_AI_DATA: AIPanelData = {
  healthScore: 92,
  revenuePotential: '$350,000',
  buyingIntent: 'High',
  nextBestAction: 'Propose expansion to the APAC regional team based on recent feature usage.',
  suggestedFollowUp: 'Schedule a Q3 roadmap review with their CTO.',
  riskLevel: 'Low',
  executiveSummary: 'Acme Corp is highly engaged. Their recent adoption of advanced analytics features suggests they are ready for an enterprise tier upgrade.',
};

const MOCK_ACTIVITIES = [
  { id: '1', icon: Target, iconGradient: 'from-violet-600 to-indigo-600', title: 'Opportunity Created', detail: 'Expansion Deal - Q3', timestamp: '2 days ago' },
  { id: '2', icon: Phone, iconGradient: 'from-emerald-500 to-green-600', title: 'QBR Call completed', detail: 'Discussed adoption metrics and upcoming roadmap.', timestamp: '1 week ago' },
  { id: '3', icon: Mail, iconGradient: 'from-sky-500 to-blue-600', title: 'Support Ticket Closed', detail: 'Resolved SSO configuration issue.', timestamp: '2 weeks ago' },
];

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function AccountDetailsPage() {
  const router = useRouter();
  const { id } = useParams();
  
  // Real app would fetch account by id here. Using MOCK_ACCOUNT for now.
  const account = MOCK_ACCOUNT;

  const tabs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Company Details" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Website</p><p className="txt text-[13.5px] mt-1"><a href={`https://${account.website}`} className="hover:text-[var(--accent)]">{account.website}</a></p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Industry</p><p className="txt text-[13.5px] mt-1">{account.industry}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Company Size</p><p className="txt text-[13.5px] mt-1">{account.companySize}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Annual Revenue</p><p className="txt text-[13.5px] mt-1">{account.annualRevenue}</p></div>
              </div>
            </div>
            
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Address" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Street</p><p className="txt text-[13.5px] mt-1">{account.address}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">City, State</p><p className="txt text-[13.5px] mt-1">{account.city}, {account.state}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Country / Postal</p><p className="txt text-[13.5px] mt-1">{account.country} {account.postalCode}</p></div>
              </div>
            </div>
          </div>
          
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="CRM Details" />
            <div className="grid gap-6 md:grid-cols-3 pt-2">
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Account Owner</p><p className="txt text-[13.5px] mt-1">{account.owner}</p></div>
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Source</p><p className="txt text-[13.5px] mt-1">{account.source}</p></div>
              <div><p className="txt-muted text-[12px] font-semibold uppercase">Description</p><p className="txt text-[13.5px] mt-1">{account.description}</p></div>
            </div>
          </div>

          {/* Related Records Widgets */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Recent Contacts" action={<button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">View all <ArrowRight className="h-3 w-3" /></button>} />
              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--surface-2)] text-[11px] font-bold text-[var(--accent)]">SC</div>
                    <div><p className="txt text-[13px] font-semibold">Sarah Chen</p><p className="txt-faint text-[11px]">CMO</p></div>
                  </div>
                  <Mail className="h-4 w-4 text-[var(--faint)]" />
                </div>
                <div className="flex items-center justify-between pb-1">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--surface-2)] text-[11px] font-bold text-[var(--accent)]">JD</div>
                    <div><p className="txt text-[13px] font-semibold">John Doe</p><p className="txt-faint text-[11px]">VP of Sales</p></div>
                  </div>
                  <Phone className="h-4 w-4 text-[var(--faint)]" />
                </div>
              </div>
            </div>

            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Open Opportunities" action={<button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80">View all <ArrowRight className="h-3 w-3" /></button>} />
              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div><p className="txt text-[13px] font-semibold">Enterprise Expansion - Q3</p><p className="txt-faint text-[11px]">Negotiation</p></div>
                  <span className="font-display txt text-[14px] font-bold">$150,000</span>
                </div>
                <div className="flex items-center justify-between pb-1">
                  <div><p className="txt text-[13px] font-semibold">Add-on Licenses</p><p className="txt-faint text-[11px]">Proposal Sent</p></div>
                  <span className="font-display txt text-[14px] font-bold">$25,000</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      ),
    },
    { id: 'contacts', label: 'Contacts', content: <div className="p-4 text-[13px] txt-faint">Contacts list coming soon.</div> },
    { id: 'opportunities', label: 'Opportunities', content: <div className="p-4 text-[13px] txt-faint">Opportunities list coming soon.</div> },
    { id: 'meetings', label: 'Meetings', content: <div className="p-4 text-[13px] txt-faint">No upcoming meetings.</div> },
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
    { id: 'notes', label: 'Notes', content: <div className="p-4 text-[13px] txt-faint">No notes available.</div> },
    { id: 'files', label: 'Files', content: <div className="p-4 text-[13px] txt-faint">No files uploaded.</div> },
    { id: 'timeline', label: 'Timeline', content: <div className="p-4 text-[13px] txt-faint">Timeline view coming soon.</div> },
  ];

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      
      {/* ── Page Header ── */}
      <div className="flex flex-col gap-4">
        <button onClick={() => router.push('/accounts')} className="txt-muted hover:txt flex w-fit items-center gap-1 text-[13px] font-medium transition-colors">
          <ArrowLeft className="h-4 w-4" /> Back to Accounts
        </button>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-amber-500 to-orange-500 shadow-sm">
              <Building2 className="h-6 w-6 text-white" />
            </div>
            <div className="mt-1">
              <div className="flex items-center gap-3">
                <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
                  {account.name}
                </h1>
                <StatusBadge label={account.status} variant="success" />
              </div>
              <div className="txt-muted mt-1.5 flex items-center gap-3 text-[13px] font-medium">
                <span>{account.industry}</span>
                <span className="flex items-center gap-1.5 border-l border-[var(--border)] pl-3"><Users className="h-4 w-4" /> {account.owner}</span>
              </div>
            </div>
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
