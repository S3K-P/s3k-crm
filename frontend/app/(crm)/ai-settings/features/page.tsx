'use client';

import { Layers } from 'lucide-react';

import AiFeaturePending from '@/components/crm/ai/AiFeaturePending';

export default function AIFeaturesPage() {
  return (
    <AiFeaturePending
      icon={Layers}
      title="Features Configuration"
      subtitle="Which AI capabilities are enabled per CRM module."
      what="Per-module AI feature toggles — lead scoring, deal intelligence, email drafting — would be set here."
    />
  );
}
