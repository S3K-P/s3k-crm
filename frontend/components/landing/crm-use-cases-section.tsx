'use client';

import { CheckCircle2 } from 'lucide-react';

export function CrmUseCasesSection() {
  const useCases = [
    {
      badge: 'SALES EXECUTION',
      title: 'Build a disciplined sales process without adding complexity',
      desc: 'Give sales representatives a simple structure for managing accounts, opportunities, activities, and follow-ups.',
      outcomes: ['Centralized records', 'Clear next actions', 'Faster follow-up'],
      gradient: 'from-blue-600 to-cyan-500',
      titleFor: 'Growing Sales Teams'
    },
    {
      badge: 'PIPELINE VISIBILITY',
      title: 'Understand revenue potential without chasing spreadsheets',
      desc: 'Give founders and sales leaders a real-time view of pipeline value, opportunity stages, risks, and expected closures.',
      outcomes: ['Live pipeline view', 'Better forecasting', 'Faster decisions'],
      gradient: 'from-orange-500 to-amber-500',
      titleFor: 'Business Leaders'
    },
    {
      badge: 'CUSTOMER RELATIONSHIPS',
      title: 'Manage complex accounts with complete relationship context',
      desc: 'Connect companies, contacts, stakeholders, opportunities, notes, activities, and account ownership in a unified customer view.',
      outcomes: ['Better account coverage', 'Stronger relationships', 'Improved coordination'],
      gradient: 'from-brand-violet to-brand-purple',
      titleFor: 'Enterprise Account Management'
    }
  ];

  return (
    <section id="solutions" className="bg-neutral-background py-32 border-t border-gray-100">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <div className="text-sm font-bold tracking-widest text-gray-400 uppercase mb-4">
            Built for Sales Growth
          </div>
          <h2 className="text-3xl md:text-5xl font-bold text-navy-900 mb-6 tracking-tight">
            A CRM designed for the way modern teams sell
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          {useCases.map((uc, i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-3xl overflow-hidden flex flex-col hover:shadow-xl transition-shadow group relative"
            >
              <div className={`h-2 bg-gradient-to-r ${uc.gradient}`} />
              <div className="p-8 flex-1 flex flex-col">
                <div className="text-[10px] font-bold tracking-wider text-gray-500 uppercase mb-6">
                  {uc.badge}
                </div>
                
                <div className="text-sm font-semibold text-gray-400 mb-2">{uc.titleFor}</div>
                <h3 className="text-2xl font-bold text-navy-900 mb-4 leading-snug">
                  {uc.title}
                </h3>
                <p className="text-gray-500 leading-relaxed mb-8 flex-1">
                  {uc.desc}
                </p>
                
                <div className="space-y-3 pt-6 border-t border-gray-100">
                  {uc.outcomes.map((outcome, j) => (
                    <div key={j} className="flex items-center gap-3">
                      <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                      <span className="text-sm font-medium text-gray-700">{outcome}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
