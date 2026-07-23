import React from 'react';
import Link from 'next/link';
import { 
  Search, Plus, Handshake, Users, Target, DollarSign, 
  Filter, MoreHorizontal, ArrowUpRight
} from 'lucide-react';
import { mockPartners } from '@/features/crm/partners/mock-data';
import { PartnerStatus } from '@/features/crm/partners/types';

function getStatusColor(status: PartnerStatus) {
  switch(status) {
    case 'Active': return 'bg-green-500/10 text-green-500 border-green-500/20';
    case 'Pending': return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';
    case 'Onboarding': return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    case 'Inactive': return 'bg-red-500/10 text-red-500 border-red-500/20';
  }
}

export default function PartnersPage() {
  const kpis = [
    { label: 'Total Partners', value: mockPartners.length, icon: Handshake, gradient: 'from-violet-500 to-purple-500' },
    { label: 'Active Leads', value: mockPartners.reduce((acc, p) => acc + p.activeLeads, 0), icon: Users, gradient: 'from-blue-500 to-cyan-500' },
    { label: 'Converted Leads', value: mockPartners.reduce((acc, p) => acc + p.convertedOpportunities, 0), icon: Target, gradient: 'from-emerald-500 to-teal-500' },
    { label: 'Revenue Generated', value: `$${(mockPartners.reduce((acc, p) => acc + p.revenueGenerated, 0) / 1000000).toFixed(1)}M`, icon: DollarSign, gradient: 'from-orange-500 to-amber-500' },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground tracking-tight mb-1">Partners</h1>
          <p className="text-sm text-muted-foreground">Manage your channel, alliance, and referral partners.</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 text-white rounded-lg font-medium text-sm shadow-sm hover:opacity-90 transition-opacity">
          <Plus className="w-4 h-4" />
          Add Partner
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, i) => (
          <div key={i} className="surface border rounded-2xl p-5 shadow-sm relative overflow-hidden group">
            <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${kpi.gradient} opacity-5 rounded-full blur-2xl -mr-10 -mt-10 group-hover:opacity-10 transition-opacity`} />
            <div className="flex items-center justify-between mb-4">
              <div className="text-sm font-medium text-muted-foreground">{kpi.label}</div>
              <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${kpi.gradient} flex items-center justify-center shadow-sm`}>
                <kpi.icon className="w-4 h-4 text-white" />
              </div>
            </div>
            <div className="text-3xl font-bold text-foreground">{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div className="surface border rounded-xl p-2 flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input 
            type="text" 
            placeholder="Search partners, accounts, contacts..." 
            className="w-full bg-transparent pl-9 pr-4 py-2 text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex items-center gap-2 sm:border-l sm:pl-3 w-full sm:w-auto">
          <button className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2 surface-2 rounded-lg text-sm font-medium border hover:border-border/80 transition-colors">
            <Filter className="w-4 h-4 text-muted-foreground" />
            Filters
          </button>
        </div>
      </div>

      {/* Data Table */}
      <div className="surface border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase text-muted-foreground bg-black/5 dark:bg-white/5 border-b">
              <tr>
                <th className="px-6 py-4 font-semibold">Partner Name</th>
                <th className="px-6 py-4 font-semibold">Type</th>
                <th className="px-6 py-4 font-semibold">Linked Account</th>
                <th className="px-6 py-4 font-semibold text-right">Leads Generated</th>
                <th className="px-6 py-4 font-semibold text-right">Leads Converted</th>
                <th className="px-6 py-4 font-semibold text-right">Revenue</th>
                <th className="px-6 py-4 font-semibold">Status</th>
                <th className="px-6 py-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {mockPartners.map((partner) => (
                <tr key={partner.id} className="hover:surface-2 transition-colors group">
                  <td className="px-6 py-4">
                    <Link href={`/partners/${partner.id}`} className="font-semibold text-foreground hover:text-violet-500 transition-colors">
                      {partner.name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">
                    {partner.type}
                  </td>
                  <td className="px-6 py-4">
                    <Link href={`/accounts/${partner.linkedAccountId}`} className="inline-flex items-center gap-1 text-violet-500 hover:underline font-medium">
                      {partner.company}
                      <ArrowUpRight className="w-3 h-3" />
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-right font-medium">
                    {partner.totalLeadsGenerated}
                  </td>
                  <td className="px-6 py-4 text-right font-medium">
                    {partner.convertedOpportunities}
                  </td>
                  <td className="px-6 py-4 text-right font-medium">
                    ${(partner.revenueGenerated / 1000).toFixed(0)}k
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2 py-1 rounded-md text-[11px] font-semibold uppercase tracking-wider border ${getStatusColor(partner.status)}`}>
                      {partner.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                      <MoreHorizontal className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        <div className="border-t p-4 flex items-center justify-between text-sm text-muted-foreground">
          <div>Showing 1 to {mockPartners.length} of {mockPartners.length} results</div>
          <div className="flex gap-2">
            <button className="px-3 py-1.5 surface-2 border rounded-md disabled:opacity-50" disabled>Previous</button>
            <button className="px-3 py-1.5 surface-2 border rounded-md disabled:opacity-50" disabled>Next</button>
          </div>
        </div>
      </div>
      
    </div>
  );
}
