'use client';

import { Zap } from 'lucide-react';

import AiUnavailable from '@/components/crm/ai/AiUnavailable';

/* ============================================================
   NEXT BEST ACTION

   This page ranked a 925-line fixture of invented opportunities
   and told the reader which deals to work on next. Acting on a
   recommendation derived from records that do not exist is the
   most costly form the dummy-data problem takes in this
   application, which is why the page now says plainly that no
   recommendation engine exists.

   The fixtures remain under `features/ai/` for the Phase 5 work;
   nothing imports them here.
   ============================================================ */

export default function NextBestActionPage() {
  return (
    <AiUnavailable
      icon={Zap}
      title="Next Best Action"
      subtitle="Which deals to work on next, and why."
      what="Ranked recommendations across your open pipeline, with the reasoning and the suggested action for each, would appear here."
    />
  );
}
