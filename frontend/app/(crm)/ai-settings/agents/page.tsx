'use client';

import { BrainCircuit } from 'lucide-react';

import AiFeaturePending from '@/components/crm/ai/AiFeaturePending';

export default function AIAgentsPage() {
  return (
    <AiFeaturePending
      icon={BrainCircuit}
      title="AI Agents"
      subtitle="Autonomous assistants working across the CRM."
      what="Configured agents, their run schedule and their most recent activity would appear here."
    />
  );
}
