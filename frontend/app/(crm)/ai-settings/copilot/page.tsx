'use client';

import { Bot } from 'lucide-react';

import AiFeaturePending from '@/components/crm/ai/AiFeaturePending';

export default function AICopilotPage() {
  return (
    <AiFeaturePending
      icon={Bot}
      title="AI Copilot"
      subtitle="The conversational assistant available across the CRM."
      what="Copilot behaviour, tone, grounding sources and per-role availability would be configured here."
    />
  );
}
