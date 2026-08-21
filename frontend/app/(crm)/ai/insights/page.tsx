'use client';

import { BrainCircuit } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

/* ============================================================
   AI INSIGHTS

   This page resolved queries against a 768-line demonstration
   dataset of invented accounts, owners, deal values and
   recommendations — rendered inside the signed-in application,
   beside real CRM data, with no indication that any of it was
   fictional. Someone could have taken "Acme Corp is at risk,
   $450k exposed" to a pipeline review.

   The mock dataset still lives under `features/ai/` for the
   Phase 5 work to build against; nothing imports it here.
   ============================================================ */

export default function AiInsightsPage() {
  return (
    <AiUnavailable
      icon={BrainCircuit}
      title="AI Insights"
      subtitle="Ask questions about your pipeline in plain language."
      what="Account intelligence reports, risk analysis and portfolio-level summaries generated from your own CRM data would appear here."
    />
  );
}
