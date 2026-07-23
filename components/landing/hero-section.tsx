'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { ArrowRight, BarChart3, CheckCircle2, ChevronRight, LayoutDashboard, Target } from 'lucide-react';

export function HeroSection() {
  return (
    <section className="relative min-h-screen pt-32 pb-20 overflow-hidden bg-navy-900 flex items-center">
      {/* Dynamic Background Gradients */}
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-brand-purple/20 rounded-full blur-[150px] opacity-70 -translate-y-1/2 translate-x-1/3" />
      <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-brand-violet/20 rounded-full blur-[150px] opacity-70 translate-y-1/3 -translate-x-1/3" />
      <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-[0.02]" />

      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-16 items-center relative z-10 w-full mt-10 lg:mt-0">
        
        {/* Left Content */}
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="space-y-8 text-center lg:text-left"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brand-violet/10 border border-brand-violet/20 text-brand-lavender text-xs font-semibold tracking-wider uppercase">
            AI-Ready Sales Operations
          </div>
          
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white leading-[1.1] tracking-tight">
            Turn every sales opportunity into <br className="hidden lg:block" />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-lavender via-brand-purple to-brand-magenta">
              measurable growth
            </span>
          </h1>
          
          <p className="text-lg text-gray-400 max-w-2xl mx-auto lg:mx-0 leading-relaxed">
            S3K CRM brings accounts, contacts, opportunities, activities, and pipeline insights into one focused workspace so your sales team can follow up faster, prioritize better, and close with confidence.
          </p>
          
          <div className="flex flex-col sm:flex-row items-center gap-4 justify-center lg:justify-start">
            <Link 
              href="/dashboard"
              className="w-full sm:w-auto px-7 py-3.5 bg-brand-violet hover:bg-brand-purple transition-all rounded-xl text-white font-semibold text-base flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(91,79,247,0.3)]"
            >
              Launch CRM Dashboard
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link 
              href="#features"
              className="w-full sm:w-auto px-7 py-3.5 bg-white/5 hover:bg-white/10 border border-white/10 transition-all rounded-xl text-white font-semibold text-base flex items-center justify-center"
            >
              Explore Features
            </Link>
          </div>

          <p className="text-sm text-gray-500 font-medium">
            Built for growing sales teams, business leaders, and enterprise account managers.
          </p>
        </motion.div>

        {/* Right Dashboard Visual */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, delay: 0.2, ease: "easeOut" }}
          className="relative lg:h-[600px] w-full hidden md:block"
        >
          {/* Main Dashboard Card */}
          <div className="absolute inset-0 bg-navy-800 rounded-2xl border border-white/10 shadow-2xl overflow-hidden flex flex-col">
            {/* Header */}
            <div className="h-14 border-b border-white/5 flex items-center justify-between px-6 bg-white/[0.02]">
              <div className="flex items-center gap-4">
                <LayoutDashboard className="w-5 h-5 text-gray-400" />
                <div className="text-sm font-medium text-gray-300">Sales Overview</div>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-500" />
                <div className="text-xs text-gray-400">Live Sync</div>
              </div>
            </div>

            {/* Dashboard Content */}
            <div className="p-6 flex-1 flex flex-col gap-6 bg-[#0B0D34]">
              {/* Top Metrics Row */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white/5 rounded-xl border border-white/5 p-4">
                  <div className="text-gray-400 text-xs mb-1">Total Pipeline Value</div>
                  <div className="text-2xl font-bold text-white">$2.4M</div>
                  <div className="text-[10px] text-green-400 mt-1 flex items-center gap-1">
                    ↑ 12% vs last month
                  </div>
                </div>
                <div className="bg-brand-violet/10 rounded-xl border border-brand-violet/20 p-4">
                  <div className="text-brand-lavender/70 text-xs mb-1">Won Deals</div>
                  <div className="text-2xl font-bold text-brand-lavender">48</div>
                  <div className="text-[10px] text-brand-lavender/70 mt-1">
                    This quarter
                  </div>
                </div>
                <div className="bg-white/5 rounded-xl border border-white/5 p-4">
                  <div className="text-gray-400 text-xs mb-1">Conversion Rate</div>
                  <div className="text-2xl font-bold text-white">24%</div>
                  <div className="text-[10px] text-green-400 mt-1">
                    ↑ 2.1% vs last month
                  </div>
                </div>
              </div>

              {/* Chart & Pipeline Area */}
              <div className="flex gap-4 flex-1">
                {/* Pipeline Chart */}
                <div className="flex-[2] bg-white/5 rounded-xl border border-white/5 p-5 flex flex-col">
                  <div className="text-sm font-medium text-white mb-4">Pipeline by Stage</div>
                  <div className="flex-1 flex items-end gap-2 px-2 pb-2">
                    {[35, 60, 45, 80, 50, 95].map((h, i) => (
                      <div key={i} className="flex-1 group relative">
                        <div 
                          className="w-full bg-gradient-to-t from-brand-violet to-brand-purple rounded-sm opacity-80 group-hover:opacity-100 transition-opacity" 
                          style={{ height: `${h}%` }} 
                        />
                      </div>
                    ))}
                  </div>
                </div>
                
                {/* Recent Activities */}
                <div className="flex-1 bg-white/5 rounded-xl border border-white/5 p-5 flex flex-col">
                  <div className="text-sm font-medium text-white mb-4">Recent Actions</div>
                  <div className="space-y-4 flex-1">
                    {[
                      { text: "Acme Corp Proposal", time: "10m ago" },
                      { text: "Call with TechFlow", time: "1h ago" },
                      { text: "Contract signed", time: "2h ago", highlight: true }
                    ].map((item, i) => (
                      <div key={i} className="flex items-start gap-3">
                        <div className={`mt-1 w-2 h-2 rounded-full ${item.highlight ? 'bg-green-400' : 'bg-brand-violet'}`} />
                        <div>
                          <div className={`text-xs ${item.highlight ? 'text-green-400 font-medium' : 'text-gray-300'}`}>{item.text}</div>
                          <div className="text-[10px] text-gray-500">{item.time}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Floating UI Elements */}
          <motion.div 
            animate={{ y: [0, -10, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
            className="absolute -right-6 top-32 bg-navy-800/90 backdrop-blur-xl border border-white/10 p-4 rounded-xl shadow-2xl flex items-center gap-4 z-20"
          >
            <div className="w-10 h-10 rounded-lg bg-green-500/20 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">Deal Closed</div>
              <div className="text-xs text-gray-400">NexaData ($120k)</div>
            </div>
          </motion.div>

          <motion.div 
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
            className="absolute -left-8 bottom-32 bg-navy-800/90 backdrop-blur-xl border border-brand-violet/30 p-4 rounded-xl shadow-2xl flex items-center gap-4 z-20"
          >
            <div className="w-10 h-10 rounded-lg bg-brand-violet/20 flex items-center justify-center">
              <Target className="w-5 h-5 text-brand-lavender" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">High Priority</div>
              <div className="text-xs text-gray-400">Follow up with Enterprise Inc.</div>
            </div>
          </motion.div>

        </motion.div>
      </div>
    </section>
  );
}
