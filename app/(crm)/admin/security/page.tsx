'use client';

import { Lock, ShieldAlert, KeyRound, Smartphone, CreditCard, DownloadCloud } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';

export default function AdminSecurityBillingPage() {
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-5xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-zinc-700 to-black">
            <Lock className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Security & Billing</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Manage authentication policies and subscription plans.</p>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        
        {/* Security Section */}
        <div className="flex flex-col gap-6">
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Authentication Policies" />
            <div className="mt-4 space-y-3">
               <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                 <div className="flex items-center gap-3">
                   <Smartphone className="h-5 w-5 text-[var(--muted)]" />
                   <div>
                     <p className="txt text-[13px] font-semibold">Multi-Factor Auth (MFA)</p>
                     <p className="txt-muted text-[11px] mt-0.5">Require MFA for all admins.</p>
                   </div>
                 </div>
                 <div className="h-5 w-9 bg-emerald-500 rounded-full flex items-center justify-end p-0.5"><div className="h-4 w-4 bg-white rounded-full" /></div>
               </div>
               <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                 <div className="flex items-center gap-3">
                   <KeyRound className="h-5 w-5 text-[var(--muted)]" />
                   <div>
                     <p className="txt text-[13px] font-semibold">Password Policy</p>
                     <p className="txt-muted text-[11px] mt-0.5">Strict (Min 12 chars, alphanumeric).</p>
                   </div>
                 </div>
                 <button className="text-[12px] font-semibold text-[var(--accent)]">Edit</button>
               </div>
            </div>
          </div>

          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="API Access" />
            <div className="mt-4">
              <p className="txt-muted text-[13px] mb-4">Manage API keys and OAuth applications used for headless integrations.</p>
              <button className="flex items-center justify-center w-full py-2.5 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] hover:border-[var(--accent)] transition-colors txt text-[13px] font-semibold">
                Manage API Keys
              </button>
            </div>
          </div>
        </div>

        {/* Billing Section */}
        <div className="flex flex-col gap-6">
          <div className="surface bd rounded-2xl border p-5 bg-gradient-to-br from-[var(--surface-2)] to-[var(--surface)]">
            <SectionHeader title="Current Plan" />
            <div className="mt-6 text-center">
              <span className="inline-block px-3 py-1 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-[11px] font-bold uppercase tracking-wider mb-2">Enterprise Tier</span>
              <h3 className="font-display txt text-[36px] font-bold leading-none">$2,500 <span className="text-[16px] txt-muted font-medium">/ month</span></h3>
              <p className="txt-muted text-[13px] mt-2">Next invoice date: Aug 1, 2026</p>
            </div>
            
            <div className="mt-8 space-y-4 border-t border-[var(--border)] pt-6">
              <div>
                <div className="flex items-center justify-between text-[12px] font-semibold txt-muted mb-1.5">
                  <span>Active Users</span>
                  <span>1,180 / 1,500</span>
                </div>
                <div className="h-1.5 w-full bg-[var(--surface)] rounded-full overflow-hidden border border-[var(--border)]">
                  <div className="h-full bg-[var(--accent)]" style={{ width: '78%' }} />
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between text-[12px] font-semibold txt-muted mb-1.5">
                  <span>Storage Usage</span>
                  <span>1.2 TB / 5 TB</span>
                </div>
                <div className="h-1.5 w-full bg-[var(--surface)] rounded-full overflow-hidden border border-[var(--border)]">
                  <div className="h-full bg-emerald-500" style={{ width: '24%' }} />
                </div>
              </div>
            </div>
            
            <div className="mt-8">
              <button className="w-full flex items-center justify-center py-2.5 rounded-lg bg-[var(--text)] text-[var(--bg)] transition hover:opacity-90 text-[13px] font-semibold">
                Manage Subscription
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
