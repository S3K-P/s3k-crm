'use client';

import { Cpu } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AIProvidersPage() {
  return (
    <AiUnavailable
      icon={Cpu}
      title="Providers & Models"
      subtitle="Model providers and per-purpose model selection."
      what="Connected providers, their API health and the default model chosen for each purpose would appear here."
    />
  );
}
