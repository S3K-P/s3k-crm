import { cn } from '@/lib/utils';
import { Sparkles, FileText, CheckSquare, Mail, AlertTriangle, Heart, Map } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';

/* ============================================================
   AI MEETING ASSISTANT
   Dedicated AI panel for Meeting detail pages.
   ============================================================ */

export interface AIMeetingAssistantData {
  summary: string;
  actionItems: string[];
  emailDraftSnippet: string;
  risksDiscussed?: string;
  customerSentiment?: 'Positive' | 'Neutral' | 'Negative';
  suggestedNextSteps: string;
}

interface AIMeetingAssistantProps {
  data: AIMeetingAssistantData;
  className?: string;
}

export default function AIMeetingAssistant({ data, className }: AIMeetingAssistantProps) {
  return (
    <div className={cn('surface bd flex flex-col gap-4 rounded-2xl border p-5', className)}>
      <div className="flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-violet-500" />
        <h3 className="font-display txt text-[16px] font-bold">Meeting Assistant</h3>
      </div>

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <FileText className="h-4 w-4 text-emerald-500" />
          <h4 className="txt text-[13px] font-semibold">Meeting Summary</h4>
        </div>
        <p className="txt-muted text-[12.5px] leading-relaxed">{data.summary}</p>
      </div>

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <CheckSquare className="h-4 w-4 text-sky-500" />
          <h4 className="txt text-[13px] font-semibold">Action Items</h4>
        </div>
        <ul className="flex flex-col gap-1.5 mt-2">
          {data.actionItems.map((item, i) => (
             <li key={i} className="flex items-start gap-2 text-[12.5px]">
               <span className="text-[var(--accent)] mt-0.5">•</span>
               <span className="txt-muted leading-snug">{item}</span>
             </li>
          ))}
        </ul>
      </div>

      {data.customerSentiment && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Heart className={cn("h-4 w-4", data.customerSentiment === 'Positive' ? 'text-emerald-500' : data.customerSentiment === 'Negative' ? 'text-rose-500' : 'text-amber-500')} />
            <h4 className="txt text-[13px] font-semibold">Customer Sentiment</h4>
          </div>
          <StatusBadge label={data.customerSentiment} variant={data.customerSentiment === 'Positive' ? 'success' : data.customerSentiment === 'Negative' ? 'danger' : 'warning'} />
        </div>
      )}

      {data.risksDiscussed && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-rose-500" />
            <h4 className="txt text-[13px] font-semibold">Risks Discussed</h4>
          </div>
          <p className="txt-muted text-[12.5px] leading-relaxed">{data.risksDiscussed}</p>
        </div>
      )}

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Mail className="h-4 w-4 text-amber-500" />
            <h4 className="txt text-[13px] font-semibold">Follow-up Email Draft</h4>
          </div>
          <button className="text-[11px] font-bold text-[var(--accent)] hover:opacity-80">COPY</button>
        </div>
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-3 mt-2">
          <p className="txt-muted text-[12px] whitespace-pre-wrap font-mono leading-relaxed">{data.emailDraftSnippet}</p>
        </div>
      </div>

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <Map className="h-4 w-4 text-violet-500" />
          <h4 className="txt text-[13px] font-semibold">Suggested Next Steps</h4>
        </div>
        <p className="txt-muted text-[12.5px] leading-relaxed">{data.suggestedNextSteps}</p>
      </div>

    </div>
  );
}
