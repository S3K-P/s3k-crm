import type { Metadata } from 'next';

import RequireAuth from '@/components/auth/RequireAuth';
import { SidebarProvider } from '@/components/crm/sidebar/SidebarContext';
import CrmShell from '@/components/crm/shared/CrmShell';
import { BRAND } from '@/config/site';

/**
 * Inside an app, the app names the page.
 *
 * The root layout titles everything "S3K Platforms", which is right for the
 * shell above the apps and wrong once you are in one — a browser tab reading
 * "S3K Platforms" while the user is looking at their pipeline tells them
 * nothing about where they are, and gives two open tabs the same name.
 */
export const metadata: Metadata = {
  title: {
    template: `%s · ${BRAND.name}`,
    default: `${BRAND.name} — ${BRAND.tagline}`,
  },
};

/* ============================================================
   CRM ROUTE GROUP LAYOUT
   Wraps all (crm) pages in the sidebar + topbar + breadcrumb
   shell. Completely independent of the existing (app) layout.

   RequireAuth gates the whole group once, so no individual page
   has to remember to. With no backend configured it is inert
   and the demonstration pages render unchanged.
   ============================================================ */

export default function CrmLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <SidebarProvider>
        <CrmShell>{children}</CrmShell>
      </SidebarProvider>
    </RequireAuth>
  );
}
