'use client';

import { Zap } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AIAutomationsPage() {
  return (
    <AiUnavailable
      icon={Zap}
      title="Automations"
      subtitle="Triggered AI actions on CRM events."
      what="Event triggers, their AI actions and their run history would be configured here."
    />
  );
}
