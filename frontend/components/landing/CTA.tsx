'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { BRAND } from '@/config/site';

export function CTA() {
  return (
    <section className="bg-navy-900 py-32 px-6">
      <div className="max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="relative rounded-[40px] overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-brand-blue/90 to-brand-cyan/90 mix-blend-multiply" />
          <div className="absolute inset-0 bg-navy-900/50 mix-blend-overlay" />
          
          {/* Abstract Shapes */}
          <div className="absolute top-0 right-0 w-96 h-96 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3" />
          <div className="absolute bottom-0 left-0 w-96 h-96 bg-brand-cyan/30 rounded-full blur-3xl translate-y-1/2 -translate-x-1/3" />

          <div className="relative z-10 px-6 py-24 md:py-32 flex flex-col items-center text-center">
            <h2 className="text-4xl md:text-6xl font-bold text-white mb-6 max-w-2xl tracking-tight">
              Ready to Transform Your Sales Process?
            </h2>
            <p className="text-xl text-white/80 max-w-2xl mb-12">
              Experience a CRM where AI works alongside your sales team to help you build stronger customer relationships and close more business.
            </p>
            <div className="flex flex-col sm:flex-row items-center gap-4 w-full sm:w-auto">
              <Link 
                href={BRAND.homeHref}
                className="w-full sm:w-auto px-8 py-4 bg-white hover:bg-gray-100 transition-colors rounded-xl text-navy-900 font-bold text-lg flex items-center justify-center shadow-xl"
              >
                Launch CRM
              </Link>
              <Link 
                href="#demo"
                className="w-full sm:w-auto px-8 py-4 bg-white/10 hover:bg-white/20 border border-white/20 transition-colors rounded-xl text-white font-bold text-lg flex items-center justify-center"
              >
                Request Demo
              </Link>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
