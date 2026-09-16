'use client';

import { Zap } from 'lucide-react';

import AiFeaturePending from '@/components/crm/ai/AiFeaturePending';

export default function AIAutomationsPage() {
  return (
    <AiFeaturePending
      icon={Zap}
      title="Automations"
      subtitle="Triggered AI actions on CRM events."
      what="Event triggers, their AI actions and their run history would be configured here."
    />
  );
}
