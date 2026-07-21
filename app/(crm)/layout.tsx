import { SidebarProvider } from '@/components/crm/sidebar/SidebarContext';
import CrmShell from '@/components/crm/shared/CrmShell';

/* ============================================================
   CRM ROUTE GROUP LAYOUT
   Wraps all (crm) pages in the sidebar + topbar + breadcrumb
   shell. Completely independent of the existing (app) layout.
   ============================================================ */

export default function CrmLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <CrmShell>{children}</CrmShell>
    </SidebarProvider>
  );
}
