'use client';

import { Bot, Sparkles, SlidersHorizontal, Settings2 } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import FormField, { FormSelect, FormInput } from '@/components/crm/forms/FormField';

export default function AICopilotSettingsPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">AI Copilot Settings</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Configure the global AI assistant behavior and UI presence.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg px-6 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            Save Configuration
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        
        {/* Settings Panel */}
        <div className="flex flex-col gap-6">
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="General Settings" />
            <div className="mt-5 space-y-4">
              <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                <div>
                  <p className="txt text-[13px] font-semibold">Enable Global Copilot</p>
                  <p className="txt-muted text-[11px] mt-0.5">Show AI floating button across all pages.</p>
                </div>
                <div className="h-5 w-9 bg-indigo-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
              </div>
              <FormField label="Keyboard Shortcut">
                <FormInput value="Ctrl + J" readOnly />
              </FormField>
              <FormField label="Sidebar Position">
                <FormSelect options={[{value: 'right', label: 'Right Side (Default)'}, {value: 'left', label: 'Left Side'}]} />
              </FormField>
            </div>
          </div>

          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Behavior & Tone" />
            <div className="mt-5 space-y-4">
              <FormField label="Response Style">
                <FormSelect options={[{value: 'concise', label: 'Concise & Direct'}, {value: 'detailed', label: 'Detailed & Explanatory'}]} />
              </FormField>
              <FormField label="Tone of Voice">
                <FormSelect options={[{value: 'professional', label: 'Professional'}, {value: 'casual', label: 'Casual'}, {value: 'enthusiastic', label: 'Enthusiastic'}]} />
              </FormField>
              <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] mt-2">
                <div>
                  <p className="txt text-[13px] font-semibold">Enable Suggested Actions</p>
                  <p className="txt-muted text-[11px] mt-0.5">Copilot will suggest buttons based on context.</p>
                </div>
                <div className="h-5 w-9 bg-indigo-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
              </div>
            </div>
          </div>
        </div>

        {/* Live Preview Panel */}
        <div className="surface bd rounded-2xl border p-5 bg-[var(--surface-2)] flex flex-col h-full min-h-[500px]">
          <SectionHeader title="Copilot Preview" />
          
          <div className="flex-1 mt-4 bg-[var(--bg)] border border-[var(--border)] rounded-xl relative overflow-hidden flex flex-col">
            <div className="p-4 border-b border-[var(--border)] bg-[var(--surface)] flex items-center gap-3">
               <Bot className="h-5 w-5 text-indigo-500" />
               <span className="font-semibold text-[14px]">CRM Copilot</span>
            </div>
            
            <div className="flex-1 p-4 flex flex-col gap-4">
              {/* User message */}
              <div className="self-end bg-[var(--surface)] border border-[var(--border)] rounded-2xl rounded-tr-sm px-4 py-2.5 max-w-[85%]">
                <p className="text-[13px]">Summarize the TechCorp opportunity.</p>
              </div>
              
              {/* AI message */}
              <div className="self-start bg-indigo-500/10 border border-indigo-500/20 text-[var(--text)] rounded-2xl rounded-tl-sm px-4 py-3 max-w-[90%]">
                <p className="text-[13px] leading-relaxed">
                  The TechCorp deal is valued at <strong>$120,000</strong> and is currently in the <strong>Negotiation</strong> stage. 
                  <br/><br/>
                  The primary roadblock is pricing approval from their CFO. I recommend sending the ROI case study to expedite the process.
                </p>
                
                {/* Suggested Action Preview */}
                <div className="mt-3 flex gap-2">
                  <button className="text-[11px] font-semibold bg-[var(--bg)] border border-[var(--border)] px-3 py-1.5 rounded-lg hover:border-indigo-500 transition-colors">
                    Draft follow-up email
                  </button>
                </div>
              </div>
            </div>
            
            <div className="p-3 border-t border-[var(--border)] bg-[var(--surface)]">
              <div className="bg-[var(--bg)] border border-[var(--border)] rounded-lg p-2.5 flex items-center justify-between text-muted text-[12px]">
                Ask Copilot anything...
                <Sparkles className="h-4 w-4" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
