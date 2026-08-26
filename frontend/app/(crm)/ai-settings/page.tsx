'use client';

import { Activity } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AISettingsDashboard() {
  return (
    <AiUnavailable
      icon={Activity}
      title="AI Overview"
      subtitle="Platform utilisation and AI performance metrics."
      what="Request volume, generated summaries, assisted opportunities and adoption trends would appear here."
    />
  );
}
