'use client';

import { motion } from 'framer-motion';
import { Mail, Users, Sparkles, TrendingUp } from 'lucide-react';

const steps = [
  {
    icon: Mail,
    title: 'Capture Leads',
    description: 'Collect leads from forms, email, LinkedIn, and campaigns automatically.',
    color: 'text-brand-blue',
    bg: 'bg-brand-blue/10',
  },
  {
    icon: Users,
    title: 'Manage Relationships',
    description: 'Convert leads into contacts, accounts, and opportunities effortlessly.',
    color: 'text-brand-cyan',
    bg: 'bg-brand-cyan/10',
  },
  {
    icon: Sparkles,
    title: 'AI Behind the Scenes',
    description: 'Generate emails, summarize meetings, score leads, and automate follow-ups.',
    color: 'text-brand-indigo',
    bg: 'bg-brand-indigo/10',
  },
  {
    icon: TrendingUp,
    title: 'Close More Deals',
    description: 'Track every opportunity in the pipeline and make data-driven decisions.',
    color: 'text-green-400',
    bg: 'bg-green-400/10',
  },
];

export function HowItWorks() {
  return (
    <section id="modules" className="bg-navy-900 py-32 relative">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
            How S3K CRM Works
          </h2>
          <p className="text-lg text-gray-400">
            A seamless, intelligent workflow designed to accelerate your sales cycle from the first touchpoint to the final handshake.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              className="bg-navy-800/50 backdrop-blur-sm border border-white/5 p-8 rounded-3xl hover:bg-white/[0.02] transition-colors group relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-white/5 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity" />
              
              <div className={`w-14 h-14 rounded-2xl ${step.bg} flex items-center justify-center mb-6`}>
                <step.icon className={`w-7 h-7 ${step.color}`} />
              </div>
              
              <h3 className="text-xl font-bold text-white mb-3">
                {step.title}
              </h3>
              <p className="text-gray-400 leading-relaxed">
                {step.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
