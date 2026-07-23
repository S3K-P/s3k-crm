'use client';

import { motion } from 'framer-motion';

const stats = [
  { value: '50K+', label: 'Leads Managed' },
  { value: '95%', label: 'Automation Accuracy' },
  { value: '3x', label: 'Sales Productivity' },
  { value: '24/7', label: 'AI Assistance' },
];

export function Stats() {
  return (
    <section className="bg-white py-12 border-y border-gray-100 relative z-20">
      <div className="max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 divide-x divide-gray-200">
          {stats.map((stat, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              className="text-center px-4"
            >
              <div className="text-4xl md:text-5xl font-bold text-navy-900 mb-2 tracking-tight">
                {stat.value}
              </div>
              <div className="text-sm font-medium text-gray-500">
                {stat.label}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
