'use client';

import { Activity } from 'lucide-react';

import AiFeaturePending from '@/components/crm/ai/AiFeaturePending';

export default function AISettingsDashboard() {
  return (
    <AiFeaturePending
      icon={Activity}
      title="AI Overview"
      subtitle="Platform utilisation and AI performance metrics."
      what="Request volume, generated summaries, assisted opportunities and adoption trends would appear here."
    />
  );
}
