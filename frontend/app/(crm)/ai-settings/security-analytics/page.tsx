'use client';

import { ShieldCheck } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AISecurityAnalyticsPage() {
  return (
    <AiUnavailable
      icon={ShieldCheck}
      title="Security & Analytics"
      subtitle="AI governance, data handling and usage analytics."
      what="Data-retention rules, redaction policy, per-user usage and spend would be reported here."
    />
  );
}
