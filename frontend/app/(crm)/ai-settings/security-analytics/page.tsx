'use client';

import { ShieldCheck } from 'lucide-react';

import AiFeaturePending from '@/components/crm/ai/AiFeaturePending';

export default function AISecurityAnalyticsPage() {
  return (
    <AiFeaturePending
      icon={ShieldCheck}
      title="Security & Analytics"
      subtitle="AI governance, data handling and usage analytics."
      what="Data-retention rules, redaction policy, per-user usage and spend would be reported here."
    />
  );
}
