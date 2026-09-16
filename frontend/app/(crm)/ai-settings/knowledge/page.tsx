'use client';

import { BookOpen } from 'lucide-react';

import AiFeaturePending from '@/components/crm/ai/AiFeaturePending';

export default function AIKnowledgePage() {
  return (
    <AiFeaturePending
      icon={BookOpen}
      title="Knowledge Base"
      subtitle="Documents the assistant can ground its answers in."
      what="Uploaded sources, their indexing state and retrieval settings would be managed here."
    />
  );
}
