'use client';

import BrandLogo from '@/components/brand/BrandLogo';
import { PLATFORM_BRAND } from '@/config/site';

/* ============================================================
   AUTH CARD

   The chrome the sign-in page uses, for the screens that sit
   beside it: forgot-password and reset-password.

   Deliberately not `OnboardingShell`, which is the same card
   plus a three-step progress indicator. Someone recovering a
   password is not part-way through creating an account, and
   showing them "Account · Organization · Apps" would say they
   are — the indicator is information, not decoration.
   ============================================================ */

export default function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{ background: 'var(--bg)' }}
    >
      <div className="w-full max-w-[400px]">
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <BrandLogo variant="icon" priority label={PLATFORM_BRAND.name} />
          <div>
            <h1 className="font-display txt text-[20px] font-extrabold tracking-tight">
              {PLATFORM_BRAND.name}
            </h1>
            <p
              className="text-[9px] font-bold uppercase tracking-[0.16em]"
              style={{ color: 'var(--accent)' }}
            >
              {PLATFORM_BRAND.tagline}
            </p>
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-6 shadow-[0_20px_50px_-24px_rgba(50,30,90,0.25)]">
          <h2 className="font-display txt text-[17px] font-bold">{title}</h2>
          {subtitle && <p className="txt-muted mt-1 text-[13px]">{subtitle}</p>}
          {children}
        </div>

        {footer && <div className="mt-5 text-center text-[12.5px]">{footer}</div>}
      </div>
    </div>
  );
}
