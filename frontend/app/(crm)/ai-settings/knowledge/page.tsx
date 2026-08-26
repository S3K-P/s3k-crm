'use client';

import { BookOpen } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

export default function AIKnowledgePage() {
  return (
    <AiUnavailable
      icon={BookOpen}
      title="Knowledge Base"
      subtitle="Documents the assistant can ground its answers in."
      what="Uploaded sources, their indexing state and retrieval settings would be managed here."
    />
  );
}
