'use client';

import { Bot } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AICopilotPage() {
  return (
    <AiUnavailable
      icon={Bot}
      title="AI Copilot"
      subtitle="The conversational assistant available across the CRM."
      what="Copilot behaviour, tone, grounding sources and per-role availability would be configured here."
    />
  );
}
