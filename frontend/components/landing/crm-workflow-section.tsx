'use client';

import { Building2, Target, CalendarClock, TrendingUp } from 'lucide-react';

const steps = [
  {
    num: '01',
    icon: Building2,
    title: 'Capture accounts and contacts',
    desc: 'Create a centralized record of every company, decision-maker, stakeholder, and customer relationship.',
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  {
    num: '02',
    icon: Target,
    title: 'Create and qualify opportunities',
    desc: 'Record potential deals, expected value, sales stage, probability, owner, and expected close date.',
    color: 'text-brand-violet',
    bg: 'bg-brand-lavender',
  },
  {
    num: '03',
    icon: CalendarClock,
    title: 'Track activities and follow-ups',
    desc: 'Plan calls, meetings, tasks, and next actions so that important opportunities never lose momentum.',
    color: 'text-brand-magenta',
    bg: 'bg-fuchsia-50',
  },
  {
    num: '04',
    icon: TrendingUp,
    title: 'Review pipeline and close',
    desc: 'Monitor pipeline health, identify stalled deals, prioritize the right opportunities, and convert qualified demand into revenue.',
    color: 'text-green-600',
    bg: 'bg-green-50',
  },
];

export function CrmWorkflowSection() {
  return (
    <section id="how-it-works" className="bg-neutral-background py-32 border-t border-gray-100">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <div className="text-sm font-bold tracking-widest text-gray-400 uppercase mb-4">
            How It Works
          </div>
          <h2 className="text-3xl md:text-5xl font-bold text-navy-900 mb-6 tracking-tight">
            From first contact to closed opportunity in four clear steps
          </h2>
          <p className="text-lg text-gray-500 leading-relaxed">
            Every customer interaction is organized into a transparent sales workflow that helps teams stay focused and leadership stay informed.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step, i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-2xl p-8 relative overflow-hidden group hover:shadow-lg transition-all hover:-translate-y-1"
            >
              <div className="absolute top-4 right-4 text-7xl font-bold text-gray-50 tracking-tighter select-none z-0">
                {step.num}
              </div>
              
              <div className="relative z-10">
                <div className={`w-14 h-14 rounded-xl ${step.bg} flex items-center justify-center mb-6`}>
                  <step.icon className={`w-7 h-7 ${step.color}`} />
                </div>
                
                <h3 className="text-xl font-bold text-navy-900 mb-3">
                  {step.title}
                </h3>
                <p className="text-gray-500 leading-relaxed text-sm">
                  {step.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
