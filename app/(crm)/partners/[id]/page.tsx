import React from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { 
  ArrowLeft, ArrowUpRight, Building2, Calendar, ChevronRight, 
  DollarSign, Globe, Target, Users, Mail, Phone, Clock,
  Sparkles, Handshake, BarChart3, Presentation, Briefcase
} from 'lucide-react';
import { mockPartners, mockPartnerLeads } from '@/features/crm/partners/mock-data';

export default function PartnerDetailsPage({ params }: { params: { id: string } }) {
  const partner = mockPartners.find(p => p.id === params.id);
  
  if (!partner) {
    notFound();
  }

  const leads = mockPartnerLeads.filter(l => l.partnerId === partner.id);

  const getStatusColor = (status: string) => {
    switch(status) {
      case 'Active': return 'bg-green-500/10 text-green-500 border-green-500/20';
      case 'Pending': return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';
      case 'Onboarding': return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'Inactive': return 'bg-red-500/10 text-red-500 border-red-500/20';
      default: return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
    }
  };

  const performanceMetrics = [
    { label: 'Leads Generated', value: partner.totalLeadsGenerated, icon: Users },
    { label: 'Qualified Leads', value: partner.qualifiedLeads, icon: Target },
    { label: 'Converted Leads', value: partner.convertedOpportunities, icon: Handshake },
    { label: 'Won Deals', value: partner.wonDeals, icon: Briefcase },
    { label: 'Conversion %', value: `${partner.conversionRate}%`, icon: BarChart3 },
    { label: 'Revenue Generated', value: `$${(partner.revenueGenerated / 1000).toFixed(0)}k`, icon: DollarSign },
    { label: 'Pipeline Value', value: `$${(partner.totalPipelineValue / 1000).toFixed(0)}k`, icon: Presentation },
    { label: 'Avg Deal Size', value: `$${(partner.averageDealSize / 1000).toFixed(0)}k`, icon: DollarSign },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      
      {/* Header with Breadcrumbs */}
      <div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
          <Link href="/partners" className="hover:text-foreground transition-colors flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" /> Partners
          </Link>
          <ChevronRight className="w-4 h-4" />
          <span className="text-foreground font-medium">{partner.name}</span>
        </div>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-500 flex items-center justify-center text-white text-2xl font-bold shadow-sm">
              {partner.name.substring(0, 2).toUpperCase()}
            </div>
            <div>
              <div className="flex items-center gap-3 mb-1">
                <h1 className="text-3xl font-bold text-foreground tracking-tight">{partner.name}</h1>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider border ${getStatusColor(partner.status)}`}>
                  {partner.status}
                </span>
              </div>
              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1"><Handshake className="w-4 h-4" /> {partner.type}</span>
                <span className="flex items-center gap-1"><Globe className="w-4 h-4" /> {partner.territory}</span>
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="px-4 py-2 surface border rounded-lg font-medium text-sm hover:surface-2 transition-colors">
              Edit
            </button>
            <button className="px-4 py-2 bg-foreground text-background rounded-lg font-medium text-sm hover:opacity-90 transition-opacity">
              Log Activity
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column */}
        <div className="lg:col-span-2 space-y-6">
          
          {/* AI Insights Card */}
          <div className="relative overflow-hidden rounded-2xl border border-violet-500/30 bg-violet-500/5 p-6 shadow-[0_8px_30px_rgba(139,92,246,0.08)]">
             <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
             <div className="relative z-10 flex gap-4">
               <div className="w-10 h-10 rounded-xl bg-violet-500 text-white flex items-center justify-center shrink-0 shadow-lg shadow-violet-500/30">
                 <Sparkles className="w-5 h-5" />
               </div>
               <div>
                 <h3 className="font-semibold text-foreground text-lg mb-2">AI Partner Insights</h3>
                 <p className="text-muted-foreground leading-relaxed mb-4">
                   This partner has generated <strong className="text-foreground">{partner.totalLeadsGenerated} leads</strong> this year with a <strong className="text-foreground">{partner.conversionRate}% conversion rate</strong>, outperforming the regional average by 18%. Pipeline velocity is strong.
                 </p>
                 <div className="flex flex-wrap gap-2">
                   <span className="text-xs font-medium px-3 py-1.5 rounded-lg bg-violet-500/10 text-violet-600 hover:bg-violet-500/20 cursor-pointer transition-colors">
                     Schedule Quarterly Review
                   </span>
                   <span className="text-xs font-medium px-3 py-1.5 rounded-lg surface border hover:surface-2 cursor-pointer transition-colors">
                     Share New Campaign
                   </span>
                   <span className="text-xs font-medium px-3 py-1.5 rounded-lg surface border hover:surface-2 cursor-pointer transition-colors">
                     Recommend Upsell
                   </span>
                 </div>
               </div>
             </div>
          </div>

          {/* Performance Metrics */}
          <div className="surface border rounded-2xl p-6">
            <h3 className="font-semibold text-lg mb-6">Partner Performance</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {performanceMetrics.map((metric, i) => (
                <div key={i} className="p-4 rounded-xl border border-border/50 bg-black/[0.02] dark:bg-white/[0.02]">
                  <div className="flex items-center gap-2 text-muted-foreground mb-2">
                    <metric.icon className="w-4 h-4" />
                    <span className="text-xs font-medium">{metric.label}</span>
                  </div>
                  <div className="text-2xl font-bold text-foreground">{metric.value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Lead Pipeline */}
          <div className="surface border rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="font-semibold text-lg">Lead Pipeline</h3>
              <button className="text-sm text-violet-500 hover:underline font-medium">View All Leads</button>
            </div>
            {leads.length > 0 ? (
              <div className="border rounded-xl overflow-hidden">
                <table className="w-full text-sm text-left">
                  <thead className="bg-black/5 dark:bg-white/5 border-b text-muted-foreground font-semibold">
                    <tr>
                      <th className="px-4 py-3">Lead Name</th>
                      <th className="px-4 py-3">Company</th>
                      <th className="px-4 py-3">Stage</th>
                      <th className="px-4 py-3">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {leads.map((lead) => (
                      <tr key={lead.id} className="hover:surface-2 transition-colors group">
                        <td className="px-4 py-3 font-medium">{lead.leadName}</td>
                        <td className="px-4 py-3 text-muted-foreground">{lead.company}</td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-1 rounded bg-black/5 dark:bg-white/5 text-xs font-medium">
                            {lead.currentStage}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {new Date(lead.createdAt).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center border border-dashed rounded-xl text-muted-foreground">
                No active leads found for this partner.
              </div>
            )}
          </div>
          
          {/* Charts (CSS Abstracted for now) */}
          <div className="grid grid-cols-2 gap-6">
             <div className="surface border rounded-2xl p-6">
                <h3 className="font-semibold text-sm mb-6">Lead Conversion Funnel</h3>
                <div className="space-y-3">
                  {[
                    { label: 'Generated', val: '100%', count: partner.totalLeadsGenerated, color: 'bg-violet-500' },
                    { label: 'Qualified', val: `${(partner.qualifiedLeads/partner.totalLeadsGenerated*100).toFixed(0)}%`, count: partner.qualifiedLeads, color: 'bg-indigo-500' },
                    { label: 'Converted', val: `${(partner.convertedOpportunities/partner.totalLeadsGenerated*100).toFixed(0)}%`, count: partner.convertedOpportunities, color: 'bg-cyan-500' },
                    { label: 'Won', val: `${(partner.wonDeals/partner.totalLeadsGenerated*100).toFixed(0)}%`, count: partner.wonDeals, color: 'bg-emerald-500' },
                  ].map((s, i) => (
                    <div key={i} className="flex items-center gap-3">
                       <div className="w-16 text-xs text-muted-foreground font-medium">{s.label}</div>
                       <div className="flex-1 h-6 bg-black/5 dark:bg-white/5 rounded-md overflow-hidden relative">
                         <div className={`h-full ${s.color} transition-all duration-1000 ease-out`} style={{ width: s.val }} />
                       </div>
                       <div className="w-8 text-right text-xs font-bold text-foreground">{s.count}</div>
                    </div>
                  ))}
                </div>
             </div>
             <div className="surface border rounded-2xl p-6 flex flex-col justify-between">
                <h3 className="font-semibold text-sm mb-4">Revenue Trend</h3>
                <div className="flex items-end gap-2 flex-1 pt-4">
                  {[30, 45, 25, 60, 80, 50, 95].map((h, i) => (
                    <div key={i} className="flex-1 group relative">
                       <div className="w-full bg-gradient-to-t from-violet-500/20 to-violet-500/80 rounded-sm opacity-80 group-hover:opacity-100 transition-opacity" style={{ height: `${h}%` }} />
                    </div>
                  ))}
                </div>
             </div>
          </div>

        </div>

        {/* Right Column */}
        <div className="space-y-6">
          
          {/* Partner Information */}
          <div className="surface border rounded-2xl p-6">
            <h3 className="font-semibold text-lg mb-4">Partner Information</h3>
            <div className="space-y-4 text-sm">
              <div className="flex flex-col gap-1">
                <span className="text-muted-foreground">Linked Account</span>
                <Link href={`/accounts/${partner.linkedAccountId}`} className="flex items-center gap-2 text-foreground font-medium hover:text-violet-500 transition-colors">
                  <Building2 className="w-4 h-4 text-violet-500" />
                  {partner.company}
                  <ArrowUpRight className="w-3 h-3" />
                </Link>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-muted-foreground">Website</span>
                <a href={`https://${partner.website}`} target="_blank" rel="noreferrer" className="text-foreground hover:underline">
                  {partner.website}
                </a>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-muted-foreground">Created Date</span>
                <span className="text-foreground">{new Date(partner.createdAt).toLocaleDateString()}</span>
              </div>
            </div>
          </div>

          {/* Activity Timeline */}
          <div className="surface border rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="font-semibold text-lg">Recent Activity</h3>
              <button className="text-sm text-violet-500 hover:underline font-medium">Add Note</button>
            </div>
            
            <div className="relative border-l border-border ml-3 space-y-6 pb-2">
              <div className="relative pl-6">
                <div className="absolute -left-2 top-0.5 w-4 h-4 rounded-full bg-blue-500 border-4 border-background" />
                <div className="text-sm font-semibold text-foreground mb-1">Quarterly Review Meeting</div>
                <div className="text-xs text-muted-foreground flex items-center gap-2 mb-2">
                  <Calendar className="w-3 h-3" /> Yesterday, 2:00 PM
                </div>
                <p className="text-sm text-muted-foreground bg-black/5 dark:bg-white/5 p-3 rounded-xl leading-relaxed">
                  Discussed Q3 targets and new campaign alignment. Partner is highly motivated.
                </p>
              </div>

              <div className="relative pl-6">
                <div className="absolute -left-2 top-0.5 w-4 h-4 rounded-full bg-emerald-500 border-4 border-background" />
                <div className="text-sm font-semibold text-foreground mb-1">Email Sent</div>
                <div className="text-xs text-muted-foreground flex items-center gap-2 mb-2">
                  <Mail className="w-3 h-3" /> Jul 20, 10:15 AM
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Sent the updated sales collateral and pricing sheets.
                </p>
              </div>

              <div className="relative pl-6">
                <div className="absolute -left-2 top-0.5 w-4 h-4 rounded-full bg-violet-500 border-4 border-background" />
                <div className="text-sm font-semibold text-foreground mb-1">Deal Won</div>
                <div className="text-xs text-muted-foreground flex items-center gap-2 mb-2">
                  <Target className="w-3 h-3" /> Jul 18, 4:45 PM
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Closed $45k deal with Enterprise Inc. via referral.
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
      
    </div>
  );
}
