'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';

export function FinalCtaSection() {
  return (
    <section className="bg-white py-24 px-6 relative z-10">
      <div className="max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="relative rounded-[40px] overflow-hidden bg-gradient-to-br from-brand-violet via-brand-purple to-brand-magenta"
        >
          {/* Decorative shapes */}
          <div className="absolute top-0 right-0 w-96 h-96 bg-white/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3" />
          <div className="absolute bottom-0 left-0 w-96 h-96 bg-black/20 rounded-full blur-3xl translate-y-1/2 -translate-x-1/3" />
          <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-10 mix-blend-overlay" />

          <div className="relative z-10 px-6 py-20 md:py-28 flex flex-col items-center text-center">
            <div className="text-xs font-bold tracking-widest text-brand-lavender uppercase mb-6">
              Ready to get started?
            </div>
            
            <h2 className="text-3xl md:text-5xl font-bold text-white mb-6 max-w-2xl tracking-tight leading-tight">
              Take control of your customer relationships and sales pipeline
            </h2>
            
            <p className="text-lg text-brand-lavender/90 max-w-2xl mb-10 leading-relaxed">
              Launch S3K CRM and give your team one place to manage accounts, contacts, opportunities, activities, and sales performance.
            </p>
            
            <div className="flex flex-col sm:flex-row items-center gap-4 w-full sm:w-auto">
              <Link
                href="/signup"
                className="w-full sm:w-auto px-8 py-4 bg-white hover:bg-gray-50 focus:ring-4 focus:ring-white/20 transition-all rounded-xl text-brand-violet font-bold text-lg flex items-center justify-center shadow-xl group"
              >
                Create your S3K account
                <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link 
                href="#features"
                className="w-full sm:w-auto px-8 py-4 bg-black/10 hover:bg-black/20 border border-white/20 focus:ring-4 focus:ring-black/10 transition-all rounded-xl text-white font-bold text-lg flex items-center justify-center"
              >
                Back to Features
              </Link>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
