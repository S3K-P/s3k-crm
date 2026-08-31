'use client';

import BrandLogo from '@/components/brand/BrandLogo';
import { PLATFORM_BRAND } from '@/config/site';

/* ============================================================
   ONBOARDING SHELL

   Shared chrome for the signup wizard, so the three steps look
   like one journey rather than three pages that happen to share
   a colour scheme. Matches the sign-in card's proportions and
   uses the same control classes — no new styling primitives.
   ============================================================ */

export const ONBOARDING_STEPS = ['Account', 'Organization', 'Apps'] as const;

export default function OnboardingShell({
  step,
  title,
  subtitle,
  children,
  footer,
  wide = false,
}: {
  /** 1-based index into `ONBOARDING_STEPS`. */
  step: number;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** The app-selection step needs more room than a login-sized card. */
  wide?: boolean;
}) {
  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{ background: 'var(--bg)' }}
    >
      <div className={`w-full ${wide ? 'max-w-[620px]' : 'max-w-[430px]'}`}>
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

        <StepIndicator current={step} />

        <div className="surface bd mt-4 rounded-2xl border p-6 shadow-[0_20px_50px_-24px_rgba(50,30,90,0.25)]">
          <h2 className="font-display txt text-[17px] font-bold">{title}</h2>
          {subtitle && <p className="txt-muted mt-1 text-[13px]">{subtitle}</p>}
          {children}
        </div>

        {footer && <div className="mt-5 text-center text-[12.5px]">{footer}</div>}
      </div>
    </div>
  );
}

/**
 * Progress through the wizard.
 *
 * `aria-current` marks the active step so a screen reader announces position
 * without relying on the colour change alone.
 */
function StepIndicator({ current }: { current: number }) {
  return (
    <ol className="flex items-center justify-center gap-2" aria-label="Setup progress">
      {ONBOARDING_STEPS.map((label, index) => {
        const position = index + 1;
        const done = position < current;
        const active = position === current;
        return (
          <li
            key={label}
            aria-current={active ? 'step' : undefined}
            className="flex items-center gap-2"
          >
            <span
              className="text-[11px] font-semibold transition-colors"
              style={{
                color: active || done ? 'var(--accent)' : 'var(--faint)',
              }}
            >
              {label}
            </span>
            {position < ONBOARDING_STEPS.length && (
              <span
                className="h-px w-6"
                style={{ background: done ? 'var(--accent)' : 'var(--border)' }}
                aria-hidden="true"
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
