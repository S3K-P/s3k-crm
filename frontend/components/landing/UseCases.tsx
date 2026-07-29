'use client';

import { motion } from 'framer-motion';
import { Briefcase, Megaphone, LineChart } from 'lucide-react';

const cases = [
  {
    title: 'Sales Teams',
    icon: Briefcase,
    desc: 'Manage pipelines, track opportunities, and close deals faster with AI-assisted workflows.',
    metric: '3x',
    metricLabel: 'Faster Sales Cycles',
    gradient: 'from-brand-blue to-brand-cyan',
  },
  {
    title: 'Marketing Teams',
    icon: Megaphone,
    desc: 'Track campaigns, capture leads seamlessly, and measure ROI across all your channels.',
    metric: '45%',
    metricLabel: 'Higher Conversion Rate',
    gradient: 'from-brand-indigo to-purple-500',
  },
  {
    title: 'Business Leaders',
    icon: LineChart,
    desc: 'Gain AI-powered insights into revenue, growth forecasts, and team performance metrics.',
    metric: '99%',
    metricLabel: 'Forecast Accuracy',
    gradient: 'from-brand-cyan to-green-400',
  }
];

export function UseCases() {
  return (
    <section className="bg-navy-900 py-32 relative">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
            Built for Every Team
          </h2>
          <p className="text-lg text-gray-400">
            S3K CRM adapts to your specific needs, providing the right tools and insights for every role in your organization.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          {cases.map((useCase, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              className="bg-navy-800 rounded-3xl border border-white/10 overflow-hidden group"
            >
              <div className={`h-2 bg-gradient-to-r ${useCase.gradient}`} />
              <div className="p-8">
                <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${useCase.gradient} p-[1px] mb-6 inline-block`}>
                   <div className="w-full h-full bg-navy-800 rounded-[15px] flex items-center justify-center">
                      <useCase.icon className="w-6 h-6 text-white" />
                   </div>
                </div>
                <h3 className="text-2xl font-bold text-white mb-4">{useCase.title}</h3>
                <p className="text-gray-400 leading-relaxed mb-8">{useCase.desc}</p>
                <div className="pt-6 border-t border-white/10">
                  <div className="text-4xl font-bold text-white mb-1 tracking-tight">{useCase.metric}</div>
                  <div className="text-sm text-gray-500 font-medium uppercase tracking-wider">{useCase.metricLabel}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
