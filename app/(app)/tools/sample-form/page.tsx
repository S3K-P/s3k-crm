'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import {
  FileText, Image as ImageIcon, Zap, User, Briefcase, GraduationCap,
  CheckCircle, AlertCircle, Lightbulb, Info, ChevronDown, ChevronUp,
  Sparkles, Bell, ClipboardList,
} from 'lucide-react';
import Header from '@/components/Header';
import PageHeader from '@/components/PageHeader';
import ToolWorkspace from '@/components/workspace/ToolWorkspace';

/* ============================================================
   SAMPLE TOOL PAGE — shows every form pattern in the design
   system: numbered card sections, selection cards with check
   marks, dropdown with live guide, range slider, toggle
   switches, the accent "description" panel with quality meter,
   and the gradient CTA button. All wording is placeholder —
   rename everything for your project.
   ============================================================ */

type OutputType = 'document' | 'visual';

/** Reusable pill toggle switch (accent when on). */
function Toggle({ on, onChange, disabled }: { on: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button type="button" onClick={onChange} disabled={disabled}
      className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
      style={{ background: on ? 'var(--accent)' : 'var(--border)' }}>
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${on ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
  );
}

const AUDIENCES = [
  { value: 'general',   label: 'General',   description: 'Everyday users — plain language', icon: User },
  { value: 'business',  label: 'Business',  description: 'Managers and decision makers',    icon: Briefcase },
  { value: 'technical', label: 'Technical', description: 'Specialists and power users',     icon: GraduationCap },
];

const STYLES = [
  { id: 'clean',   name: 'Clean Professional', swatches: ['#6d28d9', '#f4f4f7', '#15131f'], guide: 'Crisp corporate look — a safe default for most content.' },
  { id: 'vibrant', name: 'Vibrant',            swatches: ['#ec4899', '#f59e0b', '#0ea5e9'], guide: 'Bold colours and energy — great for consumer-facing work.' },
  { id: 'minimal', name: 'Minimal Mono',       swatches: ['#15131f', '#9a97ad', '#ffffff'], guide: 'Black-and-white restraint — an editorial, premium feel.' },
];

export default function SampleToolPage() {
  const [outputType, setOutputType] = useState<OutputType>('document');
  const [audience, setAudience] = useState('general');
  const [styleId, setStyleId] = useState('clean');
  const [numItems, setNumItems] = useState(10);
  const [quality, setQuality] = useState<'standard' | 'high'>('standard');
  const [notify, setNotify] = useState(false);
  const [reviewStep, setReviewStep] = useState(true);
  const [externalData, setExternalData] = useState(false);
  const [description, setDescription] = useState('');
  const [showGuidance, setShowGuidance] = useState(false);

  const selectedStyle = STYLES.find(s => s.id === styleId);

  const inputQuality = () => {
    const length = description.trim().length;
    if (length === 0) return { status: 'empty', message: 'Required', color: 'text-red-600' };
    if (length < 20) return { status: 'poor', message: 'Too brief - add more details', color: 'text-orange-600' };
    if (length < 50) return { status: 'fair', message: 'Good start - consider adding more specifics', color: 'text-yellow-600' };
    return { status: 'good', message: 'Excellent - detailed and specific', color: 'text-emerald-600' };
  };

  return (
    <div className="flex h-full flex-col">
      <Header />

      <ToolWorkspace>
      <PageHeader
        icon={ClipboardList}
        title="Sample Tool"
        subtitle="Every form pattern in the design system — copy this page to build your own tools"
      />

      <div className="p-8">
        <div className="max-w-5xl mx-auto space-y-8">

          {/* 1. Output type — seg cards with icon chip + check mark */}
          <div className="surface bd rounded-2xl border p-6 shadow-sm">
            <h2 className="txt mb-4 text-lg font-semibold">1. Choose an Option</h2>
            <div className="flex gap-4 flex-wrap">
              <button
                onClick={() => setOutputType('document')}
                className={`seg min-w-[140px] flex-1 p-4 text-left transition-all ${outputType === 'document' ? 'seg-on' : 'hover:opacity-80'}`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <div className="ctl p-2"><FileText className="h-6 w-6" style={{ color: 'var(--accent)' }} /></div>
                  <h3 className="txt font-semibold">Option A</h3>
                  {outputType === 'document' && <CheckCircle className="ml-auto h-5 w-5" style={{ color: 'var(--accent)' }} />}
                </div>
                <p className="txt-faint text-xs">Short description of this choice</p>
              </button>
              <button
                onClick={() => setOutputType('visual')}
                className={`seg min-w-[140px] flex-1 p-4 text-left transition-all ${outputType === 'visual' ? 'seg-on' : 'hover:opacity-80'}`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <div className="ctl p-2"><ImageIcon className="h-6 w-6" style={{ color: 'var(--accent)' }} /></div>
                  <h3 className="txt font-semibold">Option B</h3>
                  {outputType === 'visual' && <CheckCircle className="ml-auto h-5 w-5" style={{ color: 'var(--accent)' }} />}
                </div>
                <p className="txt-faint text-xs">Short description of this choice</p>
              </button>
            </div>
          </div>

          {/* 2. Audience — wide seg cards with icon + description + check */}
          <div className="surface bd rounded-2xl border p-6 shadow-sm">
            <h2 className="txt mb-4 text-lg font-semibold">2. Select Audience</h2>
            <div className="flex gap-4">
              {AUDIENCES.map((a) => {
                const isSelected = audience === a.value;
                return (
                  <button
                    key={a.value}
                    onClick={() => setAudience(a.value)}
                    className={`seg flex-1 p-4 text-left transition-all ${isSelected ? 'seg-on' : 'hover:opacity-80'}`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="ctl p-2"><a.icon className="h-6 w-6" style={{ color: isSelected ? 'var(--accent)' : 'var(--faint)' }} /></div>
                      <div className="flex-1">
                        <h3 className="txt font-semibold">{a.label}</h3>
                        <p className="txt-faint text-xs">{a.description}</p>
                      </div>
                      {isSelected && <CheckCircle className="h-5 w-5" style={{ color: 'var(--accent)' }} />}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 3. Options — dropdown with live guide, slider, two-option picker, toggles */}
          <div className="surface bd rounded-2xl border p-6 shadow-sm">
            <h2 className="txt mb-4 text-lg font-semibold">3. Options</h2>
            <div className="space-y-6">
              {/* Dropdown + live selection guide with palette swatches */}
              <div>
                <label className="txt-muted mb-2 block text-sm font-medium">Style</label>
                <select
                  value={styleId}
                  onChange={(e) => setStyleId(e.target.value)}
                  className="ctl w-full px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-violet-500/20"
                >
                  {STYLES.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                {selectedStyle && (
                  <div className="ctl mt-2 px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="flex gap-1">
                        {selectedStyle.swatches.map((c, i) => (
                          <span key={i} className="h-3.5 w-3.5 rounded-full border border-black/10" style={{ backgroundColor: c }} />
                        ))}
                      </div>
                      <span className="txt-muted text-xs font-medium">{selectedStyle.name}</span>
                    </div>
                    <p className="txt-faint text-xs mt-1.5">{selectedStyle.guide}</p>
                  </div>
                )}
              </div>

              {/* Range slider with tick labels */}
              <div>
                <label className="txt-muted mb-3 block text-sm font-medium">
                  Quantity: {numItems}
                </label>
                <input type="range" min="1" max="25" step="1" value={numItems}
                  onChange={(e) => setNumItems(Number(e.target.value))}
                  className="w-full cursor-pointer"
                />
                <div className="txt-faint flex justify-between text-xs mt-1">
                  <span>1</span><span>12</span><span>25</span>
                </div>
              </div>

              {/* Two-option seg picker */}
              <div>
                <label className="txt-muted mb-3 block text-sm font-medium">Output Quality</label>
                <div className="flex gap-4">
                  <button onClick={() => setQuality('standard')}
                    className={`seg flex-1 p-3 text-center ${quality === 'standard' ? 'seg-on' : 'hover:opacity-80'}`}>
                    <div className="txt font-medium">Standard</div>
                    <p className="txt-faint text-xs">Faster · everyday use</p>
                  </button>
                  <button onClick={() => setQuality('high')}
                    className={`seg flex-1 p-3 text-center ${quality === 'high' ? 'seg-on' : 'hover:opacity-80'}`}>
                    <div className="txt font-medium">High</div>
                    <p className="txt-faint text-xs">Best result · takes longer</p>
                  </button>
                </div>
                <p className="txt-faint text-xs mt-2">Use the helper line under a picker to explain the trade-off between the choices.</p>
              </div>

              {/* Prominent toggle row inside a seg frame */}
              <div className="seg flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <div className="ctl p-2">
                    <Bell className="h-5 w-5" style={{ color: 'var(--accent)' }} />
                  </div>
                  <div>
                    <label className="txt-muted text-sm font-medium">Notify When Finished</label>
                    <p className="txt-faint text-xs">Send an alert when the task completes</p>
                  </div>
                </div>
                <Toggle on={notify} onChange={() => setNotify(!notify)} />
              </div>

              {/* Plain toggle row */}
              <div className="flex items-center justify-between">
                <div>
                  <label className="txt-muted text-sm font-medium">Enable Review Step</label>
                  <p className="txt-faint text-xs">Require approval before the result is published</p>
                </div>
                <Toggle on={reviewStep} onChange={() => setReviewStep(!reviewStep)} />
              </div>
            </div>
          </div>

          {/* Optional feature card with toggle */}
          <div className="surface bd flex items-start justify-between gap-4 rounded-2xl border p-4 shadow-sm">
            <div>
              <p className="txt text-sm font-medium">Use External Data (optional)</p>
              <p className="txt-faint text-xs mt-1">
                When enabled, connected external sources are used in addition to your own data.
              </p>
            </div>
            <Toggle on={externalData} onChange={() => setExternalData(!externalData)} />
          </div>

          {/* Description — the accent-bordered required panel */}
          <div className="rounded-2xl border-2 p-6 shadow-sm" style={{ borderColor: 'var(--accent)', background: 'var(--accent-soft)' }}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Lightbulb className="h-5 w-5" style={{ color: 'var(--accent)' }} />
                <label className="txt text-base font-semibold">
                  Description <span className="text-red-500">*</span>
                </label>
              </div>
              <button type="button" onClick={() => setShowGuidance(!showGuidance)}
                className="flex items-center gap-1 text-sm font-medium hover:opacity-80" style={{ color: 'var(--accent)' }}>
                <Info className="h-4 w-4" />
                {showGuidance ? 'Hide' : 'Show'} Guidance
                {showGuidance ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
            </div>

            {showGuidance && (
              <div className="surface bd mb-4 rounded-xl border p-4">
                <h4 className="txt mb-2 flex items-center gap-2 text-sm font-semibold">
                  <Sparkles className="h-4 w-4" style={{ color: 'var(--accent)' }} /> What to Include:
                </h4>
                <ul className="txt-muted space-y-1 text-xs">
                  <li><strong>Goal:</strong> What should the result achieve?</li>
                  <li><strong>Details:</strong> What specifics matter most?</li>
                  <li><strong>Constraints:</strong> Anything to avoid or require?</li>
                  <li><strong>Audience:</strong> Who is this for?</li>
                </ul>
              </div>
            )}

            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what you need — goal, key details, constraints, audience…"
              rows={6}
              className={`txt w-full resize-none rounded-xl border-2 px-4 py-3 text-sm outline-none focus:ring-2 ${
                description.trim().length === 0
                  ? 'border-red-300 bg-red-50 focus:border-red-500 focus:ring-red-500/20'
                  : 'surface focus:ring-violet-500/20'
              }`}
              style={description.trim().length === 0 ? undefined : { borderColor: 'var(--accent)' }}
            />

            <div className="mt-3 flex items-center justify-between">
              <span className={`text-xs font-medium ${inputQuality().color} flex items-center gap-1`}>
                {description.trim().length > 0 && (
                  inputQuality().status === 'good' ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />
                )}
                {inputQuality().message}
              </span>
              <span className="txt-faint text-xs">{description.trim().length} characters</span>
            </div>
          </div>

          {/* Gradient CTA button */}
          <div className="flex justify-center">
            <button
              onClick={() => {
                if (!description.trim()) { toast.error('Please provide a description.'); return; }
                toast.success('Submitted (demo only)');
              }}
              className="flex items-center gap-3 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-violet-500/40 transition-all hover:shadow-xl hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
            >
              <Zap className="h-5 w-5" />Submit {outputType === 'document' ? 'Option A' : 'Option B'}
            </button>
          </div>

          {/* Info Box */}
          <div className="ctl rounded-xl p-4" style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
            <p className="txt text-sm">
              <strong>Note:</strong> This page is a template — the button shows a toast instead of
              calling an API. Wire it to your backend and keep the layout.
            </p>
          </div>

        </div>
      </div>
      </ToolWorkspace>
    </div>
  );
}
