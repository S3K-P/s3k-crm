'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { BRAND } from '@/config/site';
import { Sparkles, Brain, ArrowRight, BarChart3, Users, Target, Activity } from 'lucide-react';

export function Hero() {
  return (
    <section className="relative min-h-screen pt-32 pb-20 overflow-hidden bg-navy-900 flex items-center">
      {/* Background Orbs */}
      <div className="absolute top-1/4 -left-64 w-96 h-96 bg-brand-blue/20 rounded-full blur-[120px]" />
      <div className="absolute bottom-1/4 -right-64 w-96 h-96 bg-brand-indigo/20 rounded-full blur-[120px]" />

      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-16 items-center relative z-10">
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="space-y-8 text-center lg:text-left"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-brand-cyan text-sm font-medium">
            <Sparkles className="w-4 h-4" />
            The Future of Enterprise CRM
          </div>
          
          <h1 className="text-5xl lg:text-7xl font-bold text-white leading-[1.1] tracking-tight">
            The AI CRM Built for <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-blue to-brand-cyan">
              Modern Revenue Teams
            </span>
          </h1>
          
          <p className="text-xl text-gray-400 max-w-2xl mx-auto lg:mx-0 leading-relaxed">
            Manage leads, accounts, opportunities, customer relationships, and sales workflows from one intelligent platform powered by AI.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center gap-4 justify-center lg:justify-start">
            <Link 
              href={BRAND.homeHref}
              className="w-full sm:w-auto px-8 py-4 bg-brand-blue hover:bg-brand-indigo transition-all rounded-xl text-white font-semibold text-lg flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(79,126,255,0.4)]"
            >
              Launch CRM
              <ArrowRight className="w-5 h-5" />
            </Link>
            <Link 
              href="#demo"
              className="w-full sm:w-auto px-8 py-4 bg-white/5 hover:bg-white/10 border border-white/10 transition-all rounded-xl text-white font-semibold text-lg flex items-center justify-center"
            >
              Book Demo
            </Link>
          </div>
        </motion.div>

        {/* Abstract Dashboard Mockup */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, delay: 0.2 }}
          className="relative lg:h-[600px] w-full hidden md:block"
        >
          <div className="absolute inset-0 bg-gradient-to-tr from-brand-blue/20 to-brand-cyan/20 rounded-3xl blur-2xl opacity-50" />
          
          {/* Main Dashboard Card */}
          <div className="absolute inset-0 bg-navy-800 rounded-3xl border border-white/10 shadow-2xl overflow-hidden flex flex-col">
            <div className="h-12 border-b border-white/10 flex items-center px-6 gap-2 bg-white/5">
              <div className="w-3 h-3 rounded-full bg-red-400/50" />
              <div className="w-3 h-3 rounded-full bg-yellow-400/50" />
              <div className="w-3 h-3 rounded-full bg-green-400/50" />
            </div>
            <div className="p-6 flex-1 flex gap-6">
              {/* Sidebar Mock */}
              <div className="w-16 flex flex-col gap-4">
                {[1,2,3,4,5].map(i => (
                  <div key={i} className="w-10 h-10 rounded-lg bg-white/5" />
                ))}
              </div>
              
              {/* Content Mock */}
              <div className="flex-1 flex flex-col gap-6">
                <div className="flex gap-4">
                  <div className="flex-1 h-32 rounded-2xl bg-white/5 border border-white/5 p-4 flex flex-col justify-between">
                    <div className="w-8 h-8 rounded-full bg-brand-blue/20 flex items-center justify-center">
                      <BarChart3 className="w-4 h-4 text-brand-blue" />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-white">$2.4M</div>
                      <div className="text-sm text-gray-400">Pipeline</div>
                    </div>
                  </div>
                  <div className="flex-1 h-32 rounded-2xl bg-white/5 border border-white/5 p-4 flex flex-col justify-between">
                    <div className="w-8 h-8 rounded-full bg-brand-cyan/20 flex items-center justify-center">
                      <Users className="w-4 h-4 text-brand-cyan" />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-white">845</div>
                      <div className="text-sm text-gray-400">Active Leads</div>
                    </div>
                  </div>
                </div>
                
                <div className="flex-1 rounded-2xl bg-white/5 border border-white/5 p-4 relative overflow-hidden">
                   <div className="absolute inset-0 bg-gradient-to-t from-navy-800 to-transparent" />
                   {/* Abstract bars */}
                   <div className="flex items-end h-full gap-2 px-2 pb-4 opacity-50">
                     {[40, 70, 45, 90, 65, 85, 100].map((h, i) => (
                       <div key={i} className="flex-1 bg-brand-indigo rounded-t-sm" style={{ height: `${h}%` }} />
                     ))}
                   </div>
                </div>
              </div>
            </div>
          </div>

          {/* Floating Elements */}
          <motion.div 
            animate={{ y: [0, -10, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
            className="absolute -right-12 top-20 bg-navy-800/90 backdrop-blur-xl border border-white/10 p-4 rounded-2xl shadow-xl flex items-center gap-4"
          >
            <div className="w-10 h-10 rounded-full bg-brand-cyan/20 flex items-center justify-center">
              <Brain className="w-5 h-5 text-brand-cyan" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">AI Summary</div>
              <div className="text-xs text-gray-400">Deal likely to close</div>
            </div>
          </motion.div>

          <motion.div 
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
            className="absolute -left-12 bottom-32 bg-navy-800/90 backdrop-blur-xl border border-white/10 p-4 rounded-2xl shadow-xl flex items-center gap-4"
          >
            <div className="w-10 h-10 rounded-full bg-green-500/20 flex items-center justify-center">
              <Target className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">Opportunity Won</div>
              <div className="text-xs text-gray-400">Acme Corp ($45k)</div>
            </div>
          </motion.div>

        </motion.div>
      </div>
    </section>
  );
}
