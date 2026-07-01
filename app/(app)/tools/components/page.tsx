'use client';

import { useState } from 'react';
import {
  Boxes, Check, AlertTriangle, Info, FileText, BarChart3, Palette,
  Layers, Bot, Zap, Sparkles,
} from 'lucide-react';
import Header from '@/components/Header';
import PageHeader from '@/components/PageHeader';

const TOKENS = [
  { name: '--bg',          use: 'Page background' },
  { name: '--surface',     use: 'Cards, header, modals' },
  { name: '--surface-2',   use: 'Inputs, nested surfaces' },
  { name: '--border',      use: 'All borders' },
  { name: '--text',        use: 'Primary text' },
  { name: '--muted',       use: 'Secondary text' },
  { name: '--faint',       use: 'Tertiary text, placeholders' },
  { name: '--accent',      use: 'Brand colour, buttons, active states' },
  { name: '--accent-soft', use: 'Selected-card background' },
];

/** The gradient pairs used across launcher tiles and item thumbnails. */
const GRADIENTS = [
  { label: 'Violet',  icon: FileText,  cls: 'from-violet-600 to-indigo-600' },
  { label: 'Sky',     icon: BarChart3, cls: 'from-sky-500 to-blue-600' },
  { label: 'Pink',    icon: Palette,   cls: 'from-pink-500 to-rose-500' },
  { label: 'Amber',   icon: Layers,    cls: 'from-amber-500 to-orange-500' },
  { label: 'Emerald', icon: Bot,       cls: 'from-emerald-500 to-green-600' },
];

export default function ComponentsPage() {
  const [toggleOn, setToggleOn] = useState(true);

  return (
    <div className="flex h-full flex-col">
      <Header />
      <main className="flex-1 overflow-y-auto">
      <PageHeader
        icon={Boxes}
        title="Components"
        subtitle="Colour tokens, gradients, buttons, badges — the design-system reference"
      />

      <div className="mx-auto max-w-3xl space-y-6 p-6">
        {/* Colour token swatches */}
        <div className="surface bd rounded-2xl border p-6">
          <h2 className="font-display txt text-lg font-bold">Colour tokens</h2>
          <p className="txt-muted mt-1 text-sm">Defined in <strong className="txt">app/globals.css</strong> — light and dark values.</p>
          <div className="mt-4 space-y-2">
            {TOKENS.map(t => (
              <div key={t.name} className="flex items-center gap-3">
                <div className="bd h-8 w-8 shrink-0 rounded-lg border" style={{ background: `var(${t.name})` }} />
                <code className="txt w-36 text-[13px] font-semibold">{t.name}</code>
                <span className="txt-muted text-[13px]">{t.use}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Icon gradients — the launcher / thumbnail palette */}
        <div className="surface bd rounded-2xl border p-6">
          <h2 className="font-display txt text-lg font-bold">Icon gradients</h2>
          <p className="txt-muted mt-1 text-sm">
            Used on launcher tiles, asset thumbnails and rail icons. Tailwind classes
            like <code className="ctl px-1.5 py-0.5 text-xs">bg-gradient-to-br from-violet-600 to-indigo-600</code>.
          </p>
          <div className="mt-4 grid grid-cols-2 gap-3.5 sm:grid-cols-3 lg:grid-cols-5">
            {GRADIENTS.map(g => (
              <div key={g.label} className="surface bd rounded-2xl border p-[18px] transition-all hover:-translate-y-0.5 hover:shadow-[0_16px_30px_-16px_rgba(50,30,90,0.35)]">
                <div className={`mb-3.5 flex h-[46px] w-[46px] items-center justify-center rounded-[14px] bg-gradient-to-br ${g.cls}`}>
                  <g.icon className="h-[22px] w-[22px] text-white" />
                </div>
                <div className="txt text-[13.5px] font-semibold">{g.label}</div>
                <div className="txt-faint text-[11.5px]">Launcher tile</div>
              </div>
            ))}
          </div>
        </div>

        {/* Buttons */}
        <div className="surface bd rounded-2xl border p-6">
          <h2 className="font-display txt text-lg font-bold">Buttons</h2>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-500/40 transition-all hover:shadow-xl hover:scale-105">
              <Zap className="h-4 w-4" /> Gradient CTA
            </button>
            <button className="rounded-lg px-5 py-2.5 text-sm font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
              Primary
            </button>
            <button className="ctl px-5 py-2.5 text-sm font-semibold transition hover:opacity-80">
              Secondary
            </button>
            <button className="flex items-center gap-2 rounded-xl border border-white/25 bg-gradient-to-br from-[#2a1d4d] to-[#6d28d9] px-5 py-2.5 text-sm font-semibold text-white transition hover:opacity-90">
              <Sparkles className="h-4 w-4" /> Hero style
            </button>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <span className="txt-muted text-sm">Toggle switch:</span>
            <button type="button" onClick={() => setToggleOn(!toggleOn)}
              className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
              style={{ background: toggleOn ? 'var(--accent)' : 'var(--border)' }}>
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${toggleOn ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          </div>
        </div>

        {/* Text hierarchy */}
        <div className="surface bd rounded-2xl border p-6">
          <h2 className="font-display txt text-lg font-bold">Text hierarchy</h2>
          <div className="mt-4 space-y-2">
            <p className="font-display txt text-2xl font-extrabold">Display heading (.font-display)</p>
            <p className="txt text-sm">Primary body text (.txt)</p>
            <p className="txt-muted text-sm">Secondary text (.txt-muted)</p>
            <p className="txt-faint text-sm">Tertiary / hint text (.txt-faint)</p>
            <p className="accent text-sm font-semibold">Accent text (.accent)</p>
          </div>
        </div>

        {/* Badges */}
        <div className="surface bd rounded-2xl border p-6">
          <h2 className="font-display txt text-lg font-bold">Status badges</h2>
          <div className="mt-4 flex flex-wrap gap-2.5">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-[12px] font-semibold text-emerald-600 dark:text-emerald-400">
              <Check className="h-3.5 w-3.5" /> Completed
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-3 py-1 text-[12px] font-semibold text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-3.5 w-3.5" /> Pending
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-semibold"
              style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
              <Info className="h-3.5 w-3.5" /> Accent badge
            </span>
            <span className="rounded-md bg-black/35 px-2 py-0.5 text-[10px] font-semibold text-white backdrop-blur" style={{ background: '#333a' }}>
              THUMBNAIL BADGE
            </span>
          </div>
        </div>

        {/* Info / tip boxes */}
        <div className="surface bd rounded-2xl border p-6">
          <h2 className="font-display txt text-lg font-bold">Info boxes</h2>
          <div className="mt-4 space-y-3">
            <div className="ctl rounded-xl p-4" style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
              <p className="txt text-sm"><strong>Note:</strong> Accent info box — used for notes under forms.</p>
            </div>
            <div className="ctl rounded-xl p-3 text-[11.5px] leading-snug" style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
              <span className="mb-1 flex items-center gap-1.5 font-semibold" style={{ color: 'var(--accent)' }}>
                <Info className="h-3.5 w-3.5" /> Tip
              </span>
              <span className="txt-muted">Small tip card — used in the side rails.</span>
            </div>
          </div>
        </div>
      </div>
      </main>
    </div>
  );
}
