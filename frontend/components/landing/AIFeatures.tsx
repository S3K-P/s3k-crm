'use client';

import { motion } from 'framer-motion';
import { Bot, Mail, Mic, Star, LineChart, Lightbulb, Compass, Search } from 'lucide-react';

const aiFeatures = [
  { icon: Mail, title: 'AI Email Writer', desc: 'Draft personalized emails in seconds.' },
  { icon: Mic, title: 'Meeting Summaries', desc: 'Automatically transcribe and summarize calls.' },
  { icon: Star, title: 'Lead Scoring', desc: 'Identify high-value prospects instantly.' },
  { icon: LineChart, title: 'Predictive Insights', desc: 'Forecast revenue with machine learning.' },
  { icon: Lightbulb, title: 'Opportunity Recs', desc: 'Discover hidden cross-sell opportunities.' },
  { icon: Compass, title: 'Next Best Action', desc: 'Get AI suggestions on the next step to take.' },
  { icon: LineChart, title: 'Sales Forecasting', desc: 'Predict pipeline outcomes with high accuracy.' },
  { icon: Search, title: 'Natural Language Search', desc: '"Show deals closing this month"' },
];

export function AIFeatures() {
  return (
    <section id="ai" className="bg-navy-900 py-32 relative overflow-hidden">
      {/* Background Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-brand-cyan/5 rounded-full blur-[120px] pointer-events-none" />

      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          
          <div>
            <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
              Meet Your <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-cyan to-brand-blue">AI Sales Copilot</span>
            </h2>
            <p className="text-lg text-gray-400 mb-10">
              Transform your sales process with deeply integrated AI that automates busywork and helps you focus on what matters: closing deals.
            </p>

            <div className="grid sm:grid-cols-2 gap-4">
              {aiFeatures.map((feature, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05, duration: 0.4 }}
                  className="flex items-start gap-3 p-4 rounded-xl bg-white/[0.02] border border-white/5"
                >
                  <feature.icon className="w-5 h-5 text-brand-cyan shrink-0 mt-0.5" />
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-1">{feature.title}</h4>
                    <p className="text-xs text-gray-400">{feature.desc}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>

          <motion.div 
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="relative lg:h-[600px] flex items-center justify-center"
          >
            <div className="w-full max-w-md bg-navy-800/80 backdrop-blur-xl border border-white/10 rounded-3xl shadow-2xl overflow-hidden flex flex-col">
              <div className="p-4 border-b border-white/10 flex items-center gap-3 bg-white/5">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-cyan to-brand-blue flex items-center justify-center shadow-lg">
                  <Bot className="w-5 h-5 text-white" />
                </div>
                <div>
                  <div className="font-semibold text-white">S3K Copilot</div>
                  <div className="text-xs text-brand-cyan flex items-center gap-1">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-cyan opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-brand-cyan"></span>
                    </span>
                    Online
                  </div>
                </div>
              </div>
              
              <div className="p-6 flex-1 flex flex-col gap-4 bg-gradient-to-b from-transparent to-black/20">
                <div className="bg-white/5 border border-white/5 rounded-2xl rounded-tl-none p-4 w-[85%]">
                  <p className="text-sm text-gray-300">I noticed Acme Corp just opened your proposal. Would you like me to draft a follow-up email?</p>
                </div>
                <div className="bg-brand-blue/20 border border-brand-blue/30 rounded-2xl rounded-tr-none p-4 w-[85%] self-end">
                  <p className="text-sm text-white">Yes, draft a quick check-in email referencing the pricing tier they viewed.</p>
                </div>
                <div className="bg-white/5 border border-white/5 rounded-2xl rounded-tl-none p-4 w-[95%]">
                  <p className="text-sm text-gray-300 mb-3">Here is a draft based on their activity:</p>
                  <div className="bg-navy-900 rounded-xl p-3 border border-white/5 text-xs text-gray-400">
                    <span className="text-gray-300">Subject:</span> Quick check-in on the Pro Tier proposal...
                  </div>
                  <button className="mt-3 bg-brand-blue text-white text-xs px-4 py-2 rounded-lg font-medium w-full hover:bg-brand-indigo transition-colors">
                    Send Email
                  </button>
                </div>
              </div>
              
              <div className="p-4 border-t border-white/10 bg-white/5">
                <div className="bg-navy-900 rounded-xl border border-white/10 p-3 flex items-center gap-2">
                  <div className="flex-1 text-sm text-gray-500">Ask Copilot anything...</div>
                  <div className="w-8 h-8 rounded-lg bg-brand-cyan/20 flex items-center justify-center">
                    <Mic className="w-4 h-4 text-brand-cyan" />
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

        </div>
      </div>
    </section>
  );
}
