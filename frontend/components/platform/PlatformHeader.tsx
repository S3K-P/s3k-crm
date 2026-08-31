'use client';

import Link from 'next/link';

import ThemeToggle from '@/components/ThemeToggle';
import AccountMenu from '@/components/crm/topbar/AccountMenu';
import AppLauncher from '@/components/platform/AppLauncher';
import BrandLogo from '@/components/brand/BrandLogo';
import { PLATFORM_BRAND } from '@/config/site';

/* ============================================================
   PLATFORM HEADER

   The chrome that stays put no matter which S3K app you are in:
   brand, app launcher, account.

   `AccountMenu` and `ThemeToggle` are the CRM's own components,
   reused rather than reimplemented — the alternative is two
   account menus that drift, which is exactly the "duplicate
   navigation" this work exists to remove.
   ============================================================ */

export default function PlatformHeader({ currentAppCode }: { currentAppCode?: string }) {
  return (
    <header className="surface bd flex h-[60px] shrink-0 items-center gap-3 border-b px-5">
      <Link
        href={PLATFORM_BRAND.homeHref}
        className="flex shrink-0 items-center gap-2.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded-lg"
        aria-label={`${PLATFORM_BRAND.name} home`}
      >
        <BrandLogo variant="icon" label={PLATFORM_BRAND.name} />
        <span className="font-display txt hidden text-[15px] font-extrabold tracking-tight sm:block">
          {PLATFORM_BRAND.name}
        </span>
      </Link>

      <span className="bd hidden h-5 border-l sm:block" aria-hidden="true" />

      <AppLauncher currentAppCode={currentAppCode} />

      <div className="ml-auto flex items-center gap-2.5">
        <ThemeToggle />
        <AccountMenu />
      </div>
    </header>
  );
}
