'use client';

import { motion } from 'framer-motion';
import { Star } from 'lucide-react';

const testimonials = [
  {
    quote: "S3K CRM completely transformed how our sales team operates. The AI Copilot alone saves our reps 10 hours a week on administrative tasks.",
    author: "Sarah Jenkins",
    role: "VP of Sales, TechFlow",
  },
  {
    quote: "We evaluated Salesforce and HubSpot, but S3K offered a much more intuitive interface with superior predictive forecasting out of the box.",
    author: "Michael Chen",
    role: "CRO, NexaData",
  },
  {
    quote: "The ability to ask natural language questions about our pipeline and instantly get accurate reports is nothing short of magic.",
    author: "Elena Rodriguez",
    role: "Sales Director, CloudSync",
  }
];

export function Testimonials() {
  return (
    <section className="bg-navy-900 py-32 relative">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
            Trusted by Revenue Leaders
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {testimonials.map((test, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.4 }}
              className="bg-white/[0.02] backdrop-blur-xl border border-white/10 p-8 rounded-3xl"
            >
              <div className="flex gap-1 mb-6">
                {[1, 2, 3, 4, 5].map((star) => (
                  <Star key={star} className="w-4 h-4 text-brand-cyan fill-brand-cyan" />
                ))}
              </div>
              <p className="text-gray-300 text-lg leading-relaxed mb-8">
                "{test.quote}"
              </p>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-blue to-brand-cyan p-[2px]">
                   <div className="w-full h-full bg-navy-800 rounded-full" />
                </div>
                <div>
                  <div className="text-white font-semibold">{test.author}</div>
                  <div className="text-sm text-gray-500">{test.role}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
