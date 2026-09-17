'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, Home } from 'lucide-react';
import { BREADCRUMB_LABELS, BREADCRUMB_RECORD_LABELS } from '@/config/crm-navigation';
import { useBreadcrumbTitle } from './BreadcrumbTitleContext';

/* ============================================================
   CRM BREADCRUMBS
   Path-aware breadcrumb bar for the (crm) layout.
   Resolves human-readable labels from crm-navigation config.
   ============================================================ */

/** UUID, or a plain numeric key — anything a record id looks like in a URL. */
const RECORD_ID = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)$/i;

/** Turn a slug segment into a display label: "lead-sources" -> "Lead Sources". */
function humanize(seg: string): string {
  return seg.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export default function CrmBreadcrumbs() {
  const pathname = usePathname();
  // Published by the detail page for the record it is showing, if any.
  const recordTitle = useBreadcrumbTitle();

  // Split into segments, filter blanks
  const segments = pathname.split('/').filter(Boolean);

  // Build crumbs with cumulative paths
  const crumbs = segments.map((seg, i) => {
    const configured = BREADCRUMB_LABELS[seg];
    const isLast = i === segments.length - 1;

    let label: string;
    if (configured) {
      label = configured;
    } else if (isLast && recordTitle) {
      label = recordTitle;
    } else if (RECORD_ID.test(seg)) {
      // No name to show, so name the record type rather than mangling the id.
      label = BREADCRUMB_RECORD_LABELS[segments[i - 1]] ?? 'Details';
    } else {
      label = humanize(seg);
    }

    return { label, href: '/' + segments.slice(0, i + 1).join('/') };
  });

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
              <span className="txt max-w-[320px] truncate text-[12.5px] font-semibold" title={crumb.label}>{crumb.label}</span>
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
