'use client';

import { Blocks } from 'lucide-react';

import NotConfigured from '@/components/crm/shared/NotConfigured';

/* ============================================================
   ADMIN — INTEGRATIONS

   No integration framework exists: there is no `Integration`
   model, no credential storage, no connection test and no sync.

   The previous version of this page showed six connectors, three
   of them badged "Connected" in green. Nothing was connected.
   Someone could have planned a migration around a Salesforce
   import that did not exist.
   ============================================================ */

export default function AdminIntegrationsPage() {
  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-pink-500 to-rose-600">
          <Blocks className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Integrations</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            Connections to email, calendar and external systems.
          </p>
        </div>
      </div>

      <NotConfigured
        title="No integrations are available"
        description="Nothing is connected to this CRM, and nothing can be: there is no integration framework, no credential storage and no sync worker. No data is flowing to or from any external system."
        requires="Integration + IntegrationCredential models (Phase 4)"
      />
    </div>
  );
}
