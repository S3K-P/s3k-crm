'use client';

import type { LucideIcon } from 'lucide-react';

import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import { useAiStatus } from '@/features/ai/useAiStatus';

/* ============================================================
   AI FEATURE PENDING

   The body of an AI screen whose feature has not been built yet.

   It replaces a component that told every visitor "AI is not
   connected" unconditionally — even on a deployment where AI was
   configured and working — because the screen had no feature
   behind it. Those are two different facts. This one reports the
   real connection state from `GET /ai/status`, and when AI is
   ready it says plainly that this feature is coming next.

   Nothing here renders sample output. The fixtures still under
   `features/ai/` are not imported.
   ============================================================ */

export default function AiFeaturePending({
  title,
  subtitle,
  icon: Icon,
  what,
}: {
  /** Page heading. */
  title: string;
  /** One line describing what the screen is for. */
  subtitle: string;
  icon: LucideIcon;
  /** What this screen will show once its feature exists. */
  what: string;
}) {
  const { status, error } = useAiStatus();

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">{title}</h1>
          <p className="txt-muted mt-0.5 text-[13px]">{subtitle}</p>
        </div>
      </div>

      <AiConnectionNotice status={status} error={error} pending={{ name: title, what }} />
    </div>
  );
}
