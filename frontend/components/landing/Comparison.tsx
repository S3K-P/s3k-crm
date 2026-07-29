'use client';

import { motion } from 'framer-motion';
import { X, Check } from 'lucide-react';

const traditional = [
  'Manual data entry and updates',
  'Static, backward-looking reports',
  'Generic, rule-based automation',
  'Scattered customer information',
  'Steep learning curve',
];

const s3k = [
  'AI-first data capture & enrichment',
  'Predictive analytics & forecasting',
  'Intelligent, context-aware workflows',
  'Centralized customer intelligence',
  'Intuitive, consumer-grade design',
];

export function Comparison() {
  return (
    <section className="bg-gray-50 py-32 relative border-t border-gray-200">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <h2 className="text-3xl md:text-5xl font-bold text-navy-900 mb-6">
            Why Choose S3K CRM
          </h2>
          <p className="text-lg text-gray-500">
            Leave behind the clunky legacy systems. Experience what happens when your CRM actually works for you.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-8 lg:gap-12 max-w-5xl mx-auto">
          {/* Traditional CRM */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="bg-white border border-gray-200 rounded-3xl p-8 lg:p-10 shadow-sm"
          >
            <div className="text-xl font-semibold text-gray-500 mb-8">Traditional CRM</div>
            <ul className="space-y-6">
              {traditional.map((item, i) => (
                <li key={i} className="flex items-start gap-4 text-gray-600">
                  <div className="mt-1 w-6 h-6 rounded-full bg-red-50 flex items-center justify-center shrink-0">
                    <X className="w-4 h-4 text-red-500" />
                  </div>
                  <span className="leading-relaxed">{item}</span>
                </li>
              ))}
            </ul>
          </motion.div>

          {/* S3K CRM */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="bg-gradient-to-b from-brand-blue/10 to-transparent border border-brand-blue/20 rounded-3xl p-8 lg:p-10 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-64 h-64 bg-brand-cyan/20 blur-[100px] rounded-full pointer-events-none" />
            
            <div className="text-xl font-bold text-white mb-8 flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-brand-blue flex items-center justify-center text-sm">S3K</div>
              CRM
            </div>
            <ul className="space-y-6 relative z-10">
              {s3k.map((item, i) => (
                <li key={i} className="flex items-start gap-4 text-white">
                  <div className="mt-1 w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center shrink-0">
                    <Check className="w-4 h-4 text-green-400" />
                  </div>
                  <span className="leading-relaxed font-medium">{item}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
