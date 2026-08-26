import RequireAuth from '@/components/auth/RequireAuth';
import { SidebarProvider } from '@/components/crm/sidebar/SidebarContext';
import CrmShell from '@/components/crm/shared/CrmShell';

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
