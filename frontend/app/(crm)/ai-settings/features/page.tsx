'use client';

import { Layers } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AIFeaturesPage() {
  return (
    <AiUnavailable
      icon={Layers}
      title="Features Configuration"
      subtitle="Which AI capabilities are enabled per CRM module."
      what="Per-module AI feature toggles — lead scoring, deal intelligence, email drafting — would be set here."
    />
  );
}
