import { cn } from '@/lib/utils';
import { Sparkles, BrainCircuit, Target, AlertTriangle, Lightbulb, MessageSquare, Briefcase } from 'lucide-react';
import StatusBadge from '@/components/crm/shared/StatusBadge';

/* ============================================================
   AI QUALIFICATION ASSISTANT
   Dedicated AI panel for the Qualification Workspace.
   ============================================================ */

export interface AIQualificationAssistantData {
  qualificationScore: number;
  buyingIntent: 'High' | 'Medium' | 'Low';
  probabilityToConvert: string;
  missingInformation: string[];
  suggestedDiscoveryQuestions: string[];
  recommendedNextActions: string[];
  executiveSummary: string;
}

interface AIQualificationAssistantProps {
  data: AIQualificationAssistantData;
  className?: string;
}

export default function AIQualificationAssistant({ data, className }: AIQualificationAssistantProps) {
  const scoreColor = data.qualificationScore >= 80 ? 'text-emerald-500' : data.qualificationScore >= 50 ? 'text-amber-500' : 'text-rose-500';
  const intentColor = data.buyingIntent === 'High' ? 'success' : data.buyingIntent === 'Medium' ? 'warning' : 'danger';

  return (
    <div className={cn('surface bd flex flex-col gap-4 rounded-2xl border p-5', className)}>
      <div className="flex items-center gap-2 mb-2">
        <BrainCircuit className="h-5 w-5 text-violet-500" />
        <h3 className="font-display txt text-[16px] font-bold">AI Qualification</h3>
      </div>

      {/* Top Metrics Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="surface-2 flex flex-col items-center justify-center rounded-xl border border-[var(--border)] py-4 text-center">
          <p className="txt-muted mb-1 text-[11px] font-semibold uppercase tracking-wider">AI Score</p>
          <span className={cn("font-display text-[28px] font-bold leading-none", scoreColor)}>
            {data.qualificationScore}
          </span>
        </div>

        <div className="flex flex-col gap-3">
          <div className="surface-2 rounded-xl border border-[var(--border)] p-2.5 flex items-center justify-between">
            <span className="txt-muted text-[11px] font-semibold uppercase">Intent</span>
            <StatusBadge label={data.buyingIntent} variant={intentColor} />
          </div>
          <div className="surface-2 rounded-xl border border-[var(--border)] p-2.5 flex flex-col">
            <span className="txt-muted text-[10px] font-semibold uppercase">Convert Prob.</span>
            <span className="font-display txt mt-0.5 text-[15px] font-bold">{data.probabilityToConvert}</span>
          </div>
        </div>
      </div>

      {/* Missing Information */}
      {data.missingInformation.length > 0 && (
        <div className="surface-2 rounded-xl border border-rose-500/20 bg-rose-500/5 p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-rose-500" />
            <h4 className="txt text-[13px] font-semibold">Missing Key Data</h4>
          </div>
          <ul className="flex flex-col gap-1.5 mt-2">
            {data.missingInformation.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px]">
                <span className="text-rose-500 mt-0.5">•</span>
                <span className="txt-muted leading-snug">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Discovery Questions */}
      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <MessageSquare className="h-4 w-4 text-sky-500" />
          <h4 className="txt text-[13px] font-semibold">Suggested Questions</h4>
        </div>
        <ul className="flex flex-col gap-2.5 mt-3">
          {data.suggestedDiscoveryQuestions.map((q, i) => (
            <li key={i} className="txt text-[12px] italic leading-relaxed border-l-2 border-[var(--border)] pl-3">
              "{q}"
            </li>
          ))}
        </ul>
      </div>

      {/* Recommended Actions */}
      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <Target className="h-4 w-4 text-emerald-500" />
          <h4 className="txt text-[13px] font-semibold">Next Actions</h4>
        </div>
        <ul className="flex flex-col gap-2 mt-2">
          {data.recommendedNextActions.map((action, i) => (
            <li key={i} className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <span className="txt-muted text-[12.5px]">{action}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Executive Summary */}
      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <Briefcase className="h-4 w-4 text-indigo-500" />
          <h4 className="txt text-[13px] font-semibold">Executive Briefing</h4>
        </div>
        <p className="txt-muted text-[12.5px] leading-relaxed">{data.executiveSummary}</p>
      </div>

    </div>
  );
}
