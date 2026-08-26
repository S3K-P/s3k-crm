'use client';

import { BrainCircuit } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AIAgentsPage() {
  return (
    <AiUnavailable
      icon={BrainCircuit}
      title="AI Agents"
      subtitle="Autonomous assistants working across the CRM."
      what="Configured agents, their run schedule and their most recent activity would appear here."
    />
  );
}
