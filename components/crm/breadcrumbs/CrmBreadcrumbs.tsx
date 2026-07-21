'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, Home } from 'lucide-react';
import { BREADCRUMB_LABELS } from '@/config/crm-navigation';

/* ============================================================
   CRM BREADCRUMBS
   Path-aware breadcrumb bar for the (crm) layout.
   Resolves human-readable labels from crm-navigation config.
   ============================================================ */

export default function CrmBreadcrumbs() {
  const pathname = usePathname();

  // Split into segments, filter blanks
  const segments = pathname.split('/').filter(Boolean);

  // Build crumbs with cumulative paths
  const crumbs = segments.map((seg, i) => ({
    label: BREADCRUMB_LABELS[seg] ?? seg.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    href: '/' + segments.slice(0, i + 1).join('/'),
  }));

  return (
    <div className="bd flex h-[42px] shrink-0 items-center gap-1.5 border-b px-5" style={{ background: 'var(--surface-2)' }}>
      <Link
        href="/dashboard"
        className="txt-faint flex items-center gap-1 text-[12.5px] font-medium transition hover:opacity-80"
      >
        <Home className="h-3.5 w-3.5" />
      </Link>

      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={crumb.href} className="flex items-center gap-1.5">
            <ChevronRight className="txt-faint h-3 w-3" />
            {isLast ? (
              <span className="txt text-[12.5px] font-semibold">{crumb.label}</span>
            ) : (
              <Link
                href={crumb.href}
                className="txt-muted text-[12.5px] font-medium transition hover:opacity-80"
              >
                {crumb.label}
              </Link>
            )}
          </span>
        );
      })}
    </div>
  );
}
