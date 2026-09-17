'use client';

import CrmSidebar from '@/components/crm/sidebar/CrmSidebar';
import CrmTopbar from '@/components/crm/topbar/CrmTopbar';
import CrmBreadcrumbs from '@/components/crm/breadcrumbs/CrmBreadcrumbs';
import { BreadcrumbTitleProvider } from '@/components/crm/breadcrumbs/BreadcrumbTitleContext';

/* ============================================================
   CRM SHELL
   Client component that composes the sidebar, topbar,
   breadcrumbs, and content area into the full CRM layout.
   ============================================================ */

export default function CrmShell({ children }: { children: React.ReactNode }) {
  return (
    // Provider spans the breadcrumb bar and the page, so a detail page
    // can publish its record name to the last crumb.
    <BreadcrumbTitleProvider>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg)' }}>
        {/* Persistent sidebar */}
        <CrmSidebar />

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col">
          <CrmTopbar />
          <CrmBreadcrumbs />
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    </BreadcrumbTitleProvider>
  );
}
