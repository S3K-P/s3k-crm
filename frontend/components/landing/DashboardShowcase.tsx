'use client';

import { motion } from 'framer-motion';

export function DashboardShowcase() {
  return (
    <section className="bg-white py-32 relative overflow-hidden border-t border-gray-200">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <h2 className="text-3xl md:text-5xl font-bold text-navy-900 mb-6">
            A Workspace Designed for Speed
          </h2>
          <p className="text-lg text-gray-500">
            Navigate between your dashboard, pipeline, and analytics with zero friction. Built for modern teams who demand performance.
          </p>
        </div>

        <div className="relative h-[600px] flex justify-center mt-10">
          {/* Analytics Card (Back Left) */}
          <motion.div
            initial={{ opacity: 0, x: 100, y: 50, rotate: 5 }}
            whileInView={{ opacity: 0.6, x: -150, y: 40, rotate: -6 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1, ease: "easeOut" }}
            className="absolute top-0 w-[80%] max-w-3xl h-[450px] bg-navy-800 rounded-3xl border border-white/10 shadow-2xl z-10"
          >
             <div className="h-12 border-b border-white/10 flex items-center px-6 gap-2 bg-white/5">
                <div className="text-sm font-medium text-white/50">Analytics</div>
             </div>
             <div className="p-8">
               <div className="w-full h-48 bg-gradient-to-t from-brand-cyan/20 to-transparent border-b-2 border-brand-cyan mt-10 rounded-t-xl" />
             </div>
          </motion.div>

          {/* Pipeline Card (Back Right) */}
          <motion.div
            initial={{ opacity: 0, x: -100, y: 50, rotate: -5 }}
            whileInView={{ opacity: 0.8, x: 150, y: 20, rotate: 6 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1, delay: 0.1, ease: "easeOut" }}
            className="absolute top-0 w-[80%] max-w-3xl h-[450px] bg-navy-800 rounded-3xl border border-white/10 shadow-2xl z-20"
          >
             <div className="h-12 border-b border-white/10 flex items-center px-6 gap-2 bg-white/5">
                <div className="text-sm font-medium text-white/50">Sales Pipeline</div>
             </div>
             <div className="p-8 flex gap-4">
               {[1,2,3,4].map(i => (
                 <div key={i} className="flex-1 bg-white/5 rounded-xl h-64 p-4 flex flex-col gap-3">
                   <div className="w-1/2 h-4 bg-white/10 rounded" />
                   <div className="w-full h-16 bg-white/10 rounded" />
                   <div className="w-full h-16 bg-white/10 rounded" />
                 </div>
               ))}
             </div>
          </motion.div>

          {/* Main Dashboard (Front Center) */}
          <motion.div
            initial={{ opacity: 0, y: 100 }}
            whileInView={{ opacity: 1, y: 0, rotate: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1, delay: 0.2, ease: "easeOut" }}
            className="absolute top-10 w-[90%] max-w-4xl h-[500px] bg-navy-800 rounded-3xl border border-white/20 shadow-[0_20px_50px_rgba(0,0,0,0.5)] z-30 flex flex-col"
          >
             <div className="h-12 border-b border-white/10 flex items-center justify-between px-6 bg-white/5">
                <div className="flex gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-400" />
                  <div className="w-3 h-3 rounded-full bg-yellow-400" />
                  <div className="w-3 h-3 rounded-full bg-green-400" />
                </div>
                <div className="text-sm font-medium text-white">Main Dashboard</div>
                <div className="w-6 h-6 rounded-full bg-white/10" />
             </div>
             <div className="flex-1 p-8 grid grid-cols-3 gap-6">
               <div className="col-span-2 space-y-6">
                 <div className="flex gap-6">
                    <div className="flex-1 h-32 bg-white/5 rounded-2xl border border-white/5 p-6 flex flex-col justify-end">
                       <div className="text-3xl font-bold text-white mb-1">2,845</div>
                       <div className="text-sm text-gray-400">Total Leads</div>
                    </div>
                    <div className="flex-1 h-32 bg-brand-blue/20 rounded-2xl border border-brand-blue/30 p-6 flex flex-col justify-end relative overflow-hidden">
                       <div className="absolute top-0 right-0 w-32 h-32 bg-brand-blue/30 blur-2xl rounded-full -mr-10 -mt-10" />
                       <div className="text-3xl font-bold text-white mb-1">$4.2M</div>
                       <div className="text-sm text-brand-blue/80">Closed Revenue</div>
                    </div>
                 </div>
                 <div className="h-48 bg-white/5 rounded-2xl border border-white/5 flex items-end p-6 gap-4">
                    {[30, 40, 25, 60, 45, 80, 50, 95].map((h, i) => (
                      <div key={i} className="flex-1 bg-gradient-to-t from-brand-cyan to-brand-blue rounded-t-sm" style={{ height: `${h}%` }} />
                    ))}
                 </div>
               </div>
               <div className="bg-white/5 rounded-2xl border border-white/5 p-6 space-y-4">
                 <div className="text-sm font-medium text-white mb-4">Recent Activity</div>
                 {[1,2,3,4,5].map(i => (
                   <div key={i} className="flex items-center gap-3">
                     <div className="w-8 h-8 rounded-full bg-white/10" />
                     <div className="flex-1 space-y-2">
                       <div className="w-full h-2 bg-white/10 rounded" />
                       <div className="w-2/3 h-2 bg-white/5 rounded" />
                     </div>
                   </div>
                 ))}
               </div>
             </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
