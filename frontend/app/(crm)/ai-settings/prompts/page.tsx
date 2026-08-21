'use client';

import { MessageSquareCode } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AIPromptsPage() {
  return (
    <AiUnavailable
      icon={MessageSquareCode}
      title="Prompt Library"
      subtitle="Reusable prompt templates for the sales team."
      what="Saved prompt templates, their variables and their usage would be managed here."
    />
  );
}
