'use client';

import Link from 'next/link';
import { ArrowRight, Building2, Users, Target, Kanban, CalendarClock, BarChart3 } from 'lucide-react';

export function CrmFeaturesSection() {
  const capabilities = [
    {
      badge: 'ACCOUNT MANAGEMENT',
      title: 'A complete view of every customer account',
      desc: 'Maintain company information, ownership, relationship history, open opportunities, contacts, and recent activity in one place.',
      preview: (
        <div className="h-full w-full bg-white flex flex-col pt-4 px-4 gap-2 border-t border-x border-gray-100 rounded-t-lg shadow-sm">
          <div className="flex items-center gap-3 pb-3 border-b border-gray-100">
             <div className="w-8 h-8 rounded bg-gray-100 flex items-center justify-center"><Building2 className="w-4 h-4 text-gray-500" /></div>
             <div>
               <div className="text-xs font-bold text-gray-900">Acme Corporation</div>
               <div className="text-[10px] text-gray-500">Technology • Enterprise</div>
             </div>
          </div>
          <div className="flex gap-2">
            <div className="flex-1 h-12 rounded bg-gray-50 border border-gray-100 p-2">
              <div className="text-[8px] text-gray-400">Open Pipeline</div>
              <div className="text-xs font-bold text-gray-900">$120k</div>
            </div>
            <div className="flex-1 h-12 rounded bg-gray-50 border border-gray-100 p-2">
              <div className="text-[8px] text-gray-400">Owner</div>
              <div className="text-xs font-bold text-gray-900">Sarah Jenkins</div>
            </div>
          </div>
        </div>
      )
    },
    {
      badge: 'CONTACT MANAGEMENT',
      title: 'Keep every decision-maker and stakeholder connected',
      desc: 'Organize contacts by account, role, title, influence, relationship status, and communication history.',
      preview: (
        <div className="h-full w-full bg-white flex flex-col pt-4 px-4 gap-2 border-t border-x border-gray-100 rounded-t-lg shadow-sm">
          {[1,2,3].map(i => (
            <div key={i} className="flex items-center gap-3 p-2 rounded hover:bg-gray-50 border border-transparent hover:border-gray-100 transition-colors">
              <div className="w-6 h-6 rounded-full bg-brand-lavender text-brand-violet flex items-center justify-center text-[10px] font-bold">JD</div>
              <div className="flex-1">
                <div className="text-[10px] font-semibold text-gray-900">Jane Doe</div>
                <div className="text-[8px] text-gray-500">VP of Engineering</div>
              </div>
              <div className="text-[8px] px-1.5 py-0.5 rounded-full bg-green-50 text-green-600 font-medium">Champion</div>
            </div>
          ))}
        </div>
      )
    },
    {
      badge: 'OPPORTUNITY MANAGEMENT',
      title: 'Track every deal from qualification to closure',
      desc: 'Manage opportunity value, stage, probability, owner, expected close date, risks, and next actions.',
      preview: (
        <div className="h-full w-full bg-white flex flex-col p-4 gap-3 border-t border-x border-gray-100 rounded-t-lg shadow-sm">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-bold text-gray-900">Enterprise Expansion</div>
            <div className="text-[10px] font-bold text-brand-violet">$45,000</div>
          </div>
          <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
             <div className="h-full bg-brand-purple w-3/5" />
          </div>
          <div className="flex items-center justify-between mt-1">
            <div className="text-[8px] font-medium text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">Proposal Stage</div>
            <div className="text-[8px] text-gray-500">60% Prob.</div>
          </div>
        </div>
      )
    },
    {
      badge: 'VISUAL SALES PIPELINE',
      title: 'See pipeline movement before problems become surprises',
      desc: 'Review opportunities by stage, identify bottlenecks, and understand where revenue is most likely to convert.',
      preview: (
        <div className="h-full w-full bg-gray-50 flex pt-4 px-2 gap-2 border-t border-x border-gray-100 rounded-t-lg shadow-inner overflow-hidden">
           <div className="w-1/3 flex flex-col gap-2">
             <div className="text-[8px] font-semibold text-gray-500 mb-1">Qualify (2)</div>
             <div className="h-10 bg-white rounded border border-gray-200 shadow-sm" />
             <div className="h-10 bg-white rounded border border-gray-200 shadow-sm" />
           </div>
           <div className="w-1/3 flex flex-col gap-2">
             <div className="text-[8px] font-semibold text-gray-500 mb-1">Proposal (1)</div>
             <div className="h-10 bg-white rounded border border-brand-violet/30 shadow-sm relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-brand-violet" />
             </div>
           </div>
           <div className="w-1/3 flex flex-col gap-2">
             <div className="text-[8px] font-semibold text-gray-500 mb-1">Negotiation (0)</div>
             <div className="h-20 border-2 border-dashed border-gray-200 rounded flex items-center justify-center">
               <span className="text-[8px] text-gray-400">Empty</span>
             </div>
           </div>
        </div>
      )
    },
    {
      badge: 'ACTIVITY TRACKING',
      title: 'Make the next sales action impossible to miss',
      desc: 'Capture calls, meetings, emails, tasks, notes, follow-up dates, and ownership across every customer relationship.',
      preview: (
        <div className="h-full w-full bg-white flex flex-col pt-4 px-4 gap-0 border-t border-x border-gray-100 rounded-t-lg shadow-sm relative">
          <div className="absolute left-6 top-4 bottom-0 w-[1px] bg-gray-100" />
          {[
            { type: 'meeting', title: 'Discovery Call', date: 'Today, 2pm' },
            { type: 'task', title: 'Send Proposal', date: 'Tomorrow', highlight: true },
            { type: 'email', title: 'Follow-up Email', date: 'Oct 12' }
          ].map((item, i) => (
            <div key={i} className="flex gap-3 relative z-10 pb-4">
               <div className={`w-4 h-4 rounded-full mt-0.5 flex items-center justify-center border-2 border-white ${item.highlight ? 'bg-brand-violet' : 'bg-gray-200'}`} />
               <div>
                 <div className={`text-[10px] font-semibold ${item.highlight ? 'text-brand-violet' : 'text-gray-900'}`}>{item.title}</div>
                 <div className="text-[8px] text-gray-500">{item.date}</div>
               </div>
            </div>
          ))}
        </div>
      )
    },
    {
      badge: 'DASHBOARD & INSIGHTS',
      title: 'Turn CRM activity into leadership visibility',
      desc: 'Track pipeline value, open opportunities, stage conversion, won deals, pending actions, and team performance.',
      preview: (
        <div className="h-full w-full bg-white flex flex-col pt-4 px-4 gap-3 border-t border-x border-gray-100 rounded-t-lg shadow-sm">
           <div className="flex gap-2">
             <div className="flex-1 h-8 rounded bg-brand-violet/10 flex items-center justify-center">
               <span className="text-[10px] font-bold text-brand-violet">$2.4M</span>
             </div>
             <div className="flex-1 h-8 rounded bg-green-50 flex items-center justify-center">
               <span className="text-[10px] font-bold text-green-600">48 Won</span>
             </div>
           </div>
           <div className="flex items-end h-12 gap-1 px-1">
             {[40, 60, 45, 90, 75, 100].map((h, i) => (
               <div key={i} className="flex-1 bg-gradient-to-t from-gray-200 to-gray-300 rounded-t-sm" style={{ height: `${h}%` }} />
             ))}
           </div>
        </div>
      )
    }
  ];

  return (
    <section id="features" className="bg-white py-32 border-t border-gray-100">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <div className="text-sm font-bold tracking-widest text-gray-400 uppercase mb-4">
            CRM Capabilities
          </div>
          <h2 className="text-3xl md:text-5xl font-bold text-navy-900 mb-6 tracking-tight">
            Everything your sales team needs in one connected workspace
          </h2>
          <p className="text-lg text-gray-500 leading-relaxed">
            Replace scattered spreadsheets and disconnected follow-ups with a structured, easy-to-use sales operating system.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
          {capabilities.map((cap, i) => (
            <div
              key={i}
              className="bg-neutral-background border border-gray-200 rounded-2xl overflow-hidden flex flex-col group hover:shadow-md transition-shadow"
            >
              <div className="p-8 pb-6 flex-1">
                <div className="text-[10px] font-bold tracking-wider text-brand-violet uppercase mb-3">
                  {cap.badge}
                </div>
                <h3 className="text-lg font-bold text-navy-900 mb-3 leading-snug">
                  {cap.title}
                </h3>
                <p className="text-gray-500 text-sm leading-relaxed mb-6">
                  {cap.desc}
                </p>
                <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm font-semibold text-brand-violet hover:text-brand-purple transition-colors">
                  Explore capability <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
              
              <div className="h-40 bg-gray-100 border-t border-gray-200 px-8 pt-8 flex items-end justify-center overflow-hidden">
                {cap.preview}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
