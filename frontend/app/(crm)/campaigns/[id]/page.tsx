'use client';

import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Megaphone, Target, Users, Play, Pause, Copy, Download, Sparkles, Building2, TrendingUp, BarChart3, Activity } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import AICampaignInsights, { type AICampaignInsightsData } from '@/components/crm/ai/AICampaignInsights';
import AICommandBar from '@/components/crm/ai/AICommandBar';
import ActivityItem from '@/components/crm/cards/ActivityItem';
import { cn } from '@/lib/utils';

/* ============================================================
   MOCK DATA
   ============================================================ */
const MOCK_CAMPAIGN = {
  id: '1',
  name: 'Q3 Enterprise Outreach',
  type: 'Email',
  owner: 'Sarah Chen',
  startDate: '2026-07-01',
  endDate: '2026-09-30',
  budget: '$15,000',
  status: 'Active',
  targetAudience: 'CTOs, IT Directors',
  leadSource: 'Marketing - Email',
  products: 'Enterprise Suite',
};

const MOCK_RELATIONSHIPS = {
  leadsGenerated: 450,
  leadsConverted: 45,
  accountsCreated: 12,
  opportunitiesCreated: 45,
  pipelineValue: '$2,500,000',
  revenueAttributed: '$150,000',
};

const MOCK_AI_DATA: AICampaignInsightsData = {
  performanceSummary: 'The campaign is outperforming Q2 benchmarks by 15%. Open rates are solid, but click-through to the landing page has slowed in week 3.',
  predictedRoi: '185%',
  audienceQuality: 'High',
  bestPerformingChannel: 'Targeted Email Sequences (Sequence A)',
  suggestedImprovements: 'A/B test the subject lines for the week 4 email drop to re-engage the segment that hasn\'t opened previous emails.',
  recommendedNextCampaign: 'Enterprise Expansion - Q4 Follow-up (Webinar)',
  executiveSummary: 'Strong pipeline generation early in the quarter. The 10% conversion rate from lead to opportunity indicates high audience resonance.',
};

const MOCK_ACTIVITIES = [
  { id: '1', icon: Megaphone, iconGradient: 'from-sky-500 to-blue-600', title: 'Campaign Launched', detail: 'Email sequence A initiated to 5,000 contacts.', timestamp: '3 weeks ago' },
  { id: '2', icon: Target, iconGradient: 'from-amber-500 to-orange-500', title: 'Milestone Reached', detail: 'Generated 100 leads.', timestamp: '2 weeks ago' },
  { id: '3', icon: Activity, iconGradient: 'from-emerald-500 to-green-600', title: 'Opportunity Won', detail: 'First deal closed attributed to this campaign ($25k).', timestamp: '1 week ago' },
];

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function CampaignDetailsPage() {
  const router = useRouter();
  const { id } = useParams();
  
  const campaign = MOCK_CAMPAIGN;
  const rels = MOCK_RELATIONSHIPS;

  const tabs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
          {/* CRM Relationship Widgets */}
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="CRM Pipeline Impact" />
            <p className="txt-muted text-[13px] mb-4">Direct attribution of marketing efforts to sales revenue.</p>
            <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
              <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
                <div className="flex items-center gap-1.5 mb-1 text-[var(--muted)]"><Users className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">Leads</span></div>
                <span className="font-display txt text-[20px] font-bold">{rels.leadsGenerated}</span>
              </div>
              <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
                <div className="flex items-center gap-1.5 mb-1 text-[var(--muted)]"><CheckCircle2 className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">Converted</span></div>
                <span className="font-display txt text-[20px] font-bold">{rels.leadsConverted}</span>
              </div>
              <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
                <div className="flex items-center gap-1.5 mb-1 text-[var(--muted)]"><Building2 className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">Accounts</span></div>
                <span className="font-display txt text-[20px] font-bold">{rels.accountsCreated}</span>
              </div>
              <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
                <div className="flex items-center gap-1.5 mb-1 text-[var(--muted)]"><Target className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">Opps</span></div>
                <span className="font-display txt text-[20px] font-bold">{rels.opportunitiesCreated}</span>
              </div>
              <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
                <div className="flex items-center gap-1.5 mb-1 text-[var(--muted)]"><BarChart3 className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">Pipeline</span></div>
                <span className="font-display txt text-[16px] font-bold">{rels.pipelineValue}</span>
              </div>
              <div className="surface-2 rounded-xl border border-[var(--border)] p-3 bg-emerald-500/10 border-emerald-500/20">
                <div className="flex items-center gap-1.5 mb-1 text-emerald-600 dark:text-emerald-400"><TrendingUp className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">Revenue</span></div>
                <span className="font-display text-[16px] font-bold text-emerald-600 dark:text-emerald-400">{rels.revenueAttributed}</span>
              </div>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Campaign Details" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Schedule</p><p className="txt text-[13.5px] mt-1 font-medium">{campaign.startDate} to {campaign.endDate}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Target Audience</p><p className="txt text-[13.5px] mt-1">{campaign.targetAudience}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Lead Source Code</p><p className="txt text-[13.5px] mt-1 font-mono text-[var(--accent)] bg-[var(--surface-2)] inline-block px-2 py-0.5 rounded">{campaign.leadSource}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Products</p><p className="txt text-[13.5px] mt-1">{campaign.products}</p></div>
              </div>
            </div>
            
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Active Team" />
              <div className="flex flex-col gap-4 pt-2">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--surface-2)] text-[11px] font-bold text-[var(--accent)]">SC</div>
                    <div><p className="txt text-[13px] font-semibold">{campaign.owner}</p><p className="txt-faint text-[11px]">Campaign Manager</p></div>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--surface-2)] text-[11px] font-bold text-[var(--accent)]">MJ</div>
                    <div><p className="txt text-[13px] font-semibold">Mike Johnson</p><p className="txt-faint text-[11px]">Sales Lead</p></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      ),
    },
    { id: 'leads', label: 'Leads Generated', content: <div className="p-4 text-[13px] txt-faint">List of 450 generated leads coming soon.</div> },
    { id: 'opportunities', label: 'Opportunities', content: <div className="p-4 text-[13px] txt-faint">List of 45 opportunities coming soon.</div> },
    { id: 'performance', label: 'Performance', content: <div className="p-4 text-[13px] txt-faint">Detailed charts and analytics coming soon.</div> },
    { 
      id: 'timeline', 
      label: 'Timeline', 
      content: (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Campaign Activities" />
          <div className="pt-2">
            {MOCK_ACTIVITIES.map((activity, i) => (
              <ActivityItem key={activity.id} activity={activity} showConnector={i < MOCK_ACTIVITIES.length - 1} />
            ))}
          </div>
        </div>
      ) 
    },
    { id: 'notes', label: 'Notes', content: <div className="p-4 text-[13px] txt-faint">No manual notes added.</div> },
  ];

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      
      {/* ── AI Command Bar ── */}
      <AICommandBar />

      {/* ── Page Header ── */}
      <div className="flex flex-col gap-4">
        <button onClick={() => router.push('/campaigns')} className="txt-muted hover:txt flex w-fit items-center gap-1 text-[13px] font-medium transition-colors">
          <ArrowLeft className="h-4 w-4" /> Back to Campaigns
        </button>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-rose-500 to-orange-600 shadow-sm">
              <Megaphone className="h-6 w-6 text-white" />
            </div>
            <div className="mt-1">
              <div className="flex items-center gap-3">
                <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
                  {campaign.name}
                </h1>
                <StatusBadge label={campaign.status} variant="success" />
              </div>
              <div className="txt-muted mt-1.5 flex items-center gap-2 text-[13px] font-medium">
                <span className="flex items-center gap-1"><Target className="h-4 w-4" /> {campaign.type}</span>
                <span className="border-l border-[var(--border)] pl-2 ml-1">Budget: <span className="font-display font-bold txt">{campaign.budget}</span></span>
              </div>
            </div>
          </div>
          
          <div className="flex flex-wrap items-center gap-2">
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Pause className="h-4 w-4" /> Pause
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Copy className="h-4 w-4" /> Duplicate
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Download className="h-4 w-4" /> Export ROI
            </button>
            <button
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90 hover:shadow-md"
              style={{ background: 'var(--accent)' }}
            >
              <Sparkles className="h-4 w-4 text-violet-200" /> Gen. AI Report
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
          <AICampaignInsights data={MOCK_AI_DATA} />
        </div>
      </div>
    </div>
  );
}

// Dummy CheckCircle2 icon definition (used above)
function CheckCircle2(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}
