'use client';

import Link from 'next/link';
import {
  Sparkles, Upload, FileText, BarChart3, Palette, Layers, Bot, Play,
  FolderKanban, CheckSquare, Users, File,
} from 'lucide-react';
import Header from '@/components/Header';
import ToolWorkspace from '@/components/workspace/ToolWorkspace';

/* Demo data — replace the labels and wire your API in a real project. */

const launchers = [
  { title: 'Documents',  sub: 'Create & manage',   icon: FileText,  grad: 'from-violet-600 to-indigo-600', href: '/tools/sample-form' },
  { title: 'Analytics',  sub: 'Insights & trends', icon: BarChart3, grad: 'from-sky-500 to-blue-600',      href: '/tools/sample-form' },
  { title: 'Designs',    sub: 'Visual assets',     icon: Palette,   grad: 'from-pink-500 to-rose-500',     href: '/tools/sample-form' },
  { title: 'Workflows',  sub: 'Automate steps',    icon: Layers,    grad: 'from-amber-500 to-orange-500',  href: '/tools/sample-form' },
  { title: 'Assistant',  sub: 'AI-powered help',   icon: Bot,       grad: 'from-emerald-500 to-green-600', href: '/tools/sample-form' },
];

const stats = [
  { label: 'Total Items',     value: '128', icon: File },
  { label: 'Active Projects', value: '6',   icon: FolderKanban },
  { label: 'Completed Tasks', value: '24',  icon: CheckSquare },
  { label: 'Team Members',    value: '4',   icon: Users },
];

const recentWork = [
  { id: '1', title: 'Quarterly summary',   badge: 'DOC',    grad: 'from-violet-600 to-blue-600', icon: FileText,  sub: 'General · 2h ago',   playable: false },
  { id: '2', title: 'Team intro walkthrough', badge: 'MEDIA', grad: 'from-emerald-500 to-sky-500', icon: Play,    sub: 'Business · 5h ago',  playable: true },
  { id: '3', title: 'Monthly metrics',     badge: 'REPORT', grad: 'from-sky-500 to-blue-600',    icon: BarChart3, sub: 'Technical · 1d ago', playable: false },
  { id: '4', title: 'Brand style sheet',   badge: 'DESIGN', grad: 'from-pink-500 to-orange-500', icon: Palette,   sub: 'General · 2d ago',   playable: false },
];

export default function DashboardPage() {
  return (
    <div className="flex h-full flex-col">
      <Header />

      <ToolWorkspace hideSources>
      <div className="space-y-6 p-6 lg:p-8">

        {/* HERO — brand gradient with glow orbs */}
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#2a1d4d] via-[#6d28d9] to-[#9333ea] px-8 py-9 text-white">
          <div aria-hidden className="pointer-events-none absolute -right-16 -top-20 h-72 w-72 rounded-full bg-pink-500/40 blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute left-[28%] -bottom-28 h-64 w-64 rounded-full bg-sky-400/30 blur-3xl" />
          <div className="relative">
            <div className="text-[11.5px] font-semibold uppercase tracking-[0.16em] text-violet-200">Your Product Name</div>
            <h1 className="mt-2 max-w-xl font-display text-[30px] font-extrabold leading-tight tracking-tight">
              A headline that sells your product in one line.
            </h1>
            <p className="mt-2 max-w-lg text-[14px] leading-relaxed text-violet-100/90">
              Replace this supporting sentence with a short description of what your
              product does and who it helps.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/tools/sample-form" className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-[14px] font-semibold text-[#3a1d6b] shadow-[0_12px_28px_-10px_rgba(0,0,0,0.45)] transition hover:bg-violet-50">
                <Sparkles className="h-4 w-4" /> Primary Action
              </Link>
              <Link href="/tools/components" className="inline-flex items-center gap-2 rounded-xl border border-white/25 bg-white/10 px-5 py-3 text-[14px] font-semibold text-white transition hover:bg-white/20">
                <Upload className="h-4 w-4" /> Secondary Action
              </Link>
            </div>
          </div>
        </section>

        {/* LAUNCHER — gradient icon tiles */}
        <section>
          <div className="mb-3.5 flex items-center justify-between">
            <h2 className="txt font-display text-[16px] font-bold">Quick start</h2>
            <Link href="/tools/components" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>View all →</Link>
          </div>
          <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 lg:grid-cols-5">
            {launchers.map((l) => (
              <Link key={l.title} href={l.href}
                className="surface bd rounded-2xl border p-[18px] transition-all hover:-translate-y-0.5 hover:shadow-[0_16px_30px_-16px_rgba(50,30,90,0.35)]">
                <div className={`mb-3.5 flex h-[46px] w-[46px] items-center justify-center rounded-[14px] bg-gradient-to-br ${l.grad}`}>
                  <l.icon className="h-[22px] w-[22px] text-white" />
                </div>
                <div className="txt text-[13.5px] font-semibold">{l.title}</div>
                <div className="txt-faint text-[11.5px]">{l.sub}</div>
              </Link>
            ))}
          </div>
        </section>

        {/* SPLIT — at a glance + recent activity */}
        <section className="grid gap-[18px] lg:grid-cols-[1fr_1.5fr]">
          {/* At a glance */}
          <div className="surface bd rounded-2xl border p-[18px]">
            <h3 className="txt mb-1 font-display text-[15px] font-bold">At a glance</h3>
            <div className="mt-2">
              {stats.map((s) => (
                <div key={s.label} className="bd flex items-center gap-3 border-b py-3 last:border-0">
                  <div className="surface-2 flex h-[34px] w-[34px] items-center justify-center rounded-[10px]">
                    <s.icon className="h-[16px] w-[16px]" style={{ color: 'var(--accent)' }} />
                  </div>
                  <span className="txt-muted text-[13.5px] font-medium">{s.label}</span>
                  <span className="txt ml-auto font-display text-[18px] font-bold">{s.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent activity — gradient thumbnails with badge + play button */}
          <div className="surface bd rounded-2xl border p-[18px]">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="txt font-display text-[15px] font-bold">Recent activity</h3>
              <Link href="/tools/components" className="text-[12.5px] font-semibold hover:opacity-80" style={{ color: 'var(--accent)' }}>See all →</Link>
            </div>
            <div className="grid grid-cols-2 gap-3.5">
              {recentWork.map((item) => (
                <Link key={item.id} href="/tools/components"
                  className="group bd overflow-hidden rounded-xl border transition-all hover:-translate-y-0.5 hover:shadow-[0_14px_26px_-16px_rgba(50,30,90,0.4)]">
                  <div className={`relative grid h-24 place-items-center bg-gradient-to-br ${item.grad}`}>
                    <span className="absolute left-2.5 top-2.5 rounded-md bg-black/35 px-2 py-0.5 text-[10px] font-semibold text-white backdrop-blur">{item.badge}</span>
                    <item.icon className="h-7 w-7 text-white/90" />
                    {item.playable && (
                      <span className="absolute bottom-2.5 right-2.5 grid h-7 w-7 place-items-center rounded-full border border-white/40 bg-white/20 backdrop-blur">
                        <Play className="h-3 w-3 fill-white text-white" />
                      </span>
                    )}
                  </div>
                  <div className="surface px-3 py-2.5">
                    <div className="txt truncate text-[12.5px] font-semibold">{item.title}</div>
                    <div className="txt-faint mt-0.5 text-[10.5px]">{item.sub}</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      </div>
      </ToolWorkspace>
    </div>
  );
}
