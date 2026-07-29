import { cn } from '@/lib/utils';
import { Sparkles, TrendingUp, Users, Target, Lightbulb, BarChart3, AlertTriangle, ArrowRight } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';

/* ============================================================
   AI CAMPAIGN INSIGHTS
   Dedicated AI panel for Campaign detail pages.
   ============================================================ */

export interface AICampaignInsightsData {
  performanceSummary: string;
  predictedRoi: string;
  audienceQuality: 'High' | 'Medium' | 'Low';
  bestPerformingChannel: string;
  suggestedImprovements: string;
  recommendedNextCampaign: string;
  executiveSummary: string;
}

interface AICampaignInsightsProps {
  data: AICampaignInsightsData;
  className?: string;
}

export default function AICampaignInsights({ data, className }: AICampaignInsightsProps) {
  const getQualityColor = (quality: string) => {
    switch (quality) {
      case 'High': return 'text-emerald-500';
      case 'Medium': return 'text-amber-500';
      case 'Low': return 'text-rose-500';
      default: return 'text-sky-500';
    }
  };

  return (
    <div className={cn('surface bd flex flex-col gap-4 rounded-2xl border p-4 sm:p-5', className)}>
      <div className="flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-violet-500" />
        <h3 className="font-display txt text-[16px] font-bold">Campaign AI</h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="surface-2 rounded-xl border border-[var(--border)] p-3 flex flex-col justify-between">
          <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Predicted ROI</p>
          <div className="mt-1 flex items-end gap-1">
            <span className="font-display txt text-[24px] font-bold leading-none text-emerald-500">{data.predictedRoi}</span>
          </div>
        </div>

        <div className="surface-2 rounded-xl border border-[var(--border)] p-3 flex flex-col justify-between">
          <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Audience Qty.</p>
          <div className="mt-1 flex items-center gap-1.5">
            <div className={cn("h-2 w-2 rounded-full", getQualityColor(data.audienceQuality).replace('text-', 'bg-'))} />
            <span className={cn("font-display txt text-[18px] font-bold leading-none", getQualityColor(data.audienceQuality))}>{data.audienceQuality}</span>
          </div>
        </div>
      </div>

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <BarChart3 className="h-4 w-4 text-sky-500" />
          <h4 className="txt text-[13px] font-semibold">Performance Summary</h4>
        </div>
        <p className="txt-muted text-[12.5px] leading-relaxed">{data.performanceSummary}</p>
      </div>

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Target className="h-4 w-4 text-violet-500" />
          <h4 className="txt text-[13px] font-semibold">Best Channel</h4>
        </div>
        <span className="txt text-[13px] font-bold">{data.bestPerformingChannel}</span>
      </div>

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          <h4 className="txt text-[13px] font-semibold">Suggested Improvements</h4>
        </div>
        <p className="txt-muted text-[12.5px] leading-relaxed">{data.suggestedImprovements}</p>
      </div>

      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <Lightbulb className="h-4 w-4 text-emerald-500" />
          <h4 className="txt text-[13px] font-semibold">Recommended Next</h4>
        </div>
        <p className="txt-muted text-[12.5px] leading-relaxed">{data.recommendedNextCampaign}</p>
        <button className="mt-3 flex items-center gap-1 text-[11px] font-bold text-[var(--accent)] hover:opacity-80">
          GENERATE DRAFT <ArrowRight className="h-3 w-3" />
        </button>
      </div>
      
      <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
        <div className="mb-2 flex items-center gap-1.5">
          <TrendingUp className="h-4 w-4 text-indigo-500" />
          <h4 className="txt text-[13px] font-semibold">Executive Briefing</h4>
        </div>
        <p className="txt-muted text-[12.5px] leading-relaxed">{data.executiveSummary}</p>
      </div>

    </div>
  );
}
