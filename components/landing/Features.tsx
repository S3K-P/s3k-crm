'use client';

import { motion } from 'framer-motion';
import { 
  Users, Building2, Contact, Target, 
  Activity, Kanban, Calendar, 
  FileText, Mail, BarChart2, PieChart, Brain 
} from 'lucide-react';

const features = [
  { icon: Users, title: 'Lead Management', desc: 'Capture, score, and route leads automatically.' },
  { icon: Building2, title: 'Accounts', desc: 'Manage company profiles and organizational hierarchies.' },
  { icon: Contact, title: 'Contacts', desc: 'Keep track of all your key relationships in one place.' },
  { icon: Target, title: 'Opportunities', desc: 'Track deals through every stage of your pipeline.' },
  { icon: Activity, title: 'Activities', desc: 'Log calls, meetings, and tasks effortlessly.' },
  { icon: Kanban, title: 'Sales Pipeline', desc: 'Visualize your sales process with drag-and-drop boards.' },
  { icon: Calendar, title: 'Calendar', desc: 'Sync your schedule and manage meetings directly.' },
  { icon: FileText, title: 'Documents', desc: 'Store and share proposals, contracts, and collateral.' },
  { icon: Mail, title: 'Email Tracking', desc: 'Know when prospects open your emails and click links.' },
  { icon: BarChart2, title: 'Reports', desc: 'Generate customizable reports for deeper insights.' },
  { icon: PieChart, title: 'Analytics', desc: 'Track revenue, win rates, and team performance.' },
  { icon: Brain, title: 'AI Copilot', desc: 'Your intelligent assistant for everyday sales tasks.' },
];

export function Features() {
  return (
    <section id="features" className="bg-gray-50 py-32 relative border-t border-gray-200">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <h2 className="text-3xl md:text-5xl font-bold text-navy-900 mb-6">
            Everything your sales team needs in one intelligent platform.
          </h2>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05, duration: 0.4 }}
              className="p-6 rounded-2xl bg-white border border-gray-200 hover:shadow-lg hover:-translate-y-1 transition-all group"
            >
              <div className="w-12 h-12 rounded-xl bg-brand-blue/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <feature.icon className="w-6 h-6 text-brand-blue" />
              </div>
              <h3 className="text-lg font-semibold text-navy-900 mb-2">{feature.title}</h3>
              <p className="text-gray-500 text-sm leading-relaxed">{feature.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
