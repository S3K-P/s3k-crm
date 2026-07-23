'use client';

import { AlertCircle, Calendar, Clock, DollarSign, Target, TrendingUp } from 'lucide-react';

export function VisibilitySection() {
  return (
    <section className="bg-white py-32 border-t border-gray-100 overflow-hidden">
      <div className="max-w-7xl mx-auto px-6">
        <div className="max-w-3xl mb-16">
          <h2 className="text-3xl md:text-5xl font-bold text-navy-900 mb-6 tracking-tight">
            See what needs attention before the next sales review
          </h2>
          <p className="text-lg text-gray-500 leading-relaxed">
            S3K CRM helps teams identify valuable opportunities, stalled deals, overdue follow-ups, and upcoming actions from one focused dashboard.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-12 lg:gap-24 items-center">
          {/* Left Side: Pipeline & Performance */}
          <div className="relative">
            <div className="absolute -inset-4 bg-gray-50 rounded-[32px] -z-10" />
            <div className="bg-white border border-gray-200 rounded-2xl shadow-xl p-6 space-y-6">
              
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl border border-gray-100 bg-gray-50/50">
                  <div className="flex items-center gap-2 text-gray-500 mb-2">
                    <DollarSign className="w-4 h-4" />
                    <span className="text-xs font-semibold">Pipeline Value</span>
                  </div>
                  <div className="text-2xl font-bold text-navy-900">$4,250,000</div>
                </div>
                <div className="p-4 rounded-xl border border-gray-100 bg-brand-lavender/50">
                  <div className="flex items-center gap-2 text-brand-violet mb-2">
                    <Target className="w-4 h-4" />
                    <span className="text-xs font-semibold">Won vs Open</span>
                  </div>
                  <div className="text-2xl font-bold text-navy-900">48 <span className="text-sm text-gray-500 font-normal">/ 142</span></div>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-gray-100">
                <div className="flex items-center justify-between mb-4">
                  <div className="text-sm font-semibold text-gray-900">Opportunity Funnel</div>
                  <TrendingUp className="w-4 h-4 text-gray-400" />
                </div>
                <div className="space-y-3">
                  {[
                    { label: 'Lead', val: '100%', color: 'bg-gray-200' },
                    { label: 'Qualify', val: '75%', color: 'bg-brand-lavender text-brand-violet', bg: 'bg-brand-violet' },
                    { label: 'Proposal', val: '45%', color: 'bg-brand-violet text-white', bg: 'bg-brand-violet' },
                    { label: 'Negotiation', val: '25%', color: 'bg-gray-200' },
                  ].map((stage, i) => (
                    <div key={i} className="flex items-center gap-3">
                       <div className="w-20 text-xs text-gray-500">{stage.label}</div>
                       <div className="flex-1 h-6 bg-gray-50 rounded overflow-hidden">
                         <div className={`h-full ${stage.bg || 'bg-gray-300'}`} style={{ width: stage.val }} />
                       </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Insight Callout */}
              <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3">
                 <AlertCircle className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
                 <p className="text-sm text-blue-900 font-medium leading-snug">
                   Pipeline concentration is highest in the proposal stage.
                 </p>
              </div>

            </div>
          </div>

          {/* Right Side: Actions & Alerts */}
          <div className="space-y-6">
            
            <div className="bg-white border border-gray-200 rounded-2xl shadow-xl p-6">
              <div className="flex items-center justify-between mb-6">
                <div className="text-sm font-semibold text-gray-900">Priority Actions</div>
                <span className="px-2 py-1 bg-red-50 text-red-600 rounded text-xs font-bold">2 Overdue</span>
              </div>
              
              <div className="space-y-4">
                <div className="flex items-start gap-4 p-3 rounded-lg hover:bg-gray-50 border border-transparent transition-colors">
                  <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center shrink-0">
                    <Clock className="w-5 h-5 text-red-500" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-900">Follow up with TechCorp</div>
                    <div className="text-xs text-gray-500 mt-1">Stalled for 14 days in Negotiation</div>
                  </div>
                </div>

                <div className="flex items-start gap-4 p-3 rounded-lg hover:bg-gray-50 border border-transparent transition-colors">
                  <div className="w-10 h-10 rounded-full bg-orange-50 flex items-center justify-center shrink-0">
                    <Calendar className="w-5 h-5 text-orange-500" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-900">Final Presentation: Acme</div>
                    <div className="text-xs text-gray-500 mt-1">Today, 2:00 PM • Expected Close: Friday</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 flex flex-col justify-center">
                 <div className="text-2xl font-bold text-amber-600 mb-1">3</div>
                 <p className="text-xs text-amber-900 font-medium">
                   Opportunities require follow-up this week
                 </p>
              </div>
              <div className="bg-brand-lavender border border-brand-violet/20 rounded-xl p-4 flex flex-col justify-center">
                 <div className="text-2xl font-bold text-brand-violet mb-1">2</div>
                 <p className="text-xs text-brand-violet font-medium">
                   High-value deals are nearing expected close date
                 </p>
              </div>
            </div>

          </div>
        </div>
      </div>
    </section>
  );
}
