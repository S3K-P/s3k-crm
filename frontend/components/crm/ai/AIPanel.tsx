import { cn } from '@/lib/utils';
import { Sparkles, TrendingUp, AlertTriangle, Lightbulb, Map, Heart, MessageSquare, Users } from 'lucide-react';
import StatusBadge from '@/components/crm/shared/StatusBadge';

/* ============================================================
   AI PANEL
   Reusable AI insights panel for detail pages.
   ============================================================ */

export interface AIPanelData {
  // Score variants
  qualificationScore?: number;
  healthScore?: number;
  engagementScore?: number;
  
  // Specific blocks
  revenuePotential?: string;
  relationshipStrength?: 'Strong' | 'Average' | 'Weak';
  recentSentiment?: 'Positive' | 'Neutral' | 'Negative';
  preferredCommunicationStyle?: string;
  
  // Opportunity specifics
  winProbability?: number; // e.g., 85 (percentage)
  stakeholdersToEngage?: string;
  missingInformation?: string;
  
  // Standard blocks
  buyingIntent?: 'High' | 'Medium' | 'Low';
  nextBestAction?: string;
  suggestedNextAction?: string; // alias for nextBestAction
  suggestedFollowUp?: string;
  riskLevel?: 'Low' | 'Medium' | 'High';
  executiveSummary?: string;
  contactSummary?: string; // alias for executiveSummary
}

interface AIPanelProps {
  data: AIPanelData;
  className?: string;
}

export default function AIPanel({ data, className }: AIPanelProps) {
  const getIntentVariant = (intent: string) => {
    switch (intent) {
      case 'High': return 'success';
      case 'Medium': return 'warning';
      case 'Low': return 'neutral';
      default: return 'neutral';
    }
  };

  const getRiskVariant = (risk: string) => {
    switch (risk) {
      case 'Low': return 'success';
      case 'Medium': return 'warning';
      case 'High': return 'danger';
      default: return 'neutral';
    }
  };
  
  const getRelationshipVariant = (rel: string) => {
    switch (rel) {
      case 'Strong': return 'success';
      case 'Average': return 'warning';
      case 'Weak': return 'danger';
      default: return 'neutral';
    }
  };

  const scoreLabel = data.engagementScore ? 'Engagement' : 'Health Score';
  const scoreValue = data.engagementScore ?? data.healthScore ?? data.qualificationScore ?? '--';

  return (
    <div className={cn('surface bd flex flex-col gap-4 rounded-2xl border p-5', className)}>
      <div className="flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-violet-500" />
        <h3 className="font-display txt text-[16px] font-bold">AI Insights</h3>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
          <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider">{scoreLabel}</p>
          <div className="mt-1 flex items-end gap-1">
            <span className="font-display txt text-[24px] font-bold leading-none">{scoreValue}</span>
            <span className="txt-faint text-[12px] font-medium leading-tight">/100</span>
          </div>
        </div>

        {data.winProbability !== undefined && (
          <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
            <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Win Prob.</p>
            <div className="mt-1 flex items-end gap-1">
              <span className="font-display txt text-[24px] font-bold leading-none text-emerald-500">{data.winProbability}</span>
              <span className="txt-faint text-[12px] font-medium leading-tight">%</span>
            </div>
          </div>
        )}

        {data.buyingIntent && (
          <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
            <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Intent</p>
            <div className="mt-1">
              <StatusBadge label={data.buyingIntent} variant={getIntentVariant(data.buyingIntent)} />
            </div>
          </div>
        )}
        
        {data.relationshipStrength && (
          <div className="surface-2 rounded-xl border border-[var(--border)] p-3">
            <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Relationship</p>
            <div className="mt-1">
              <StatusBadge label={data.relationshipStrength} variant={getRelationshipVariant(data.relationshipStrength)} />
            </div>
          </div>
        )}
      </div>

      {data.revenuePotential && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <p className="txt-muted text-[11px] font-semibold uppercase tracking-wider mb-1">Revenue Forecast</p>
          <p className="font-display txt text-[20px] font-bold leading-tight">{data.revenuePotential}</p>
        </div>
      )}
      
      {data.recentSentiment && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Heart className={cn("h-4 w-4", data.recentSentiment === 'Positive' ? 'text-emerald-500' : data.recentSentiment === 'Negative' ? 'text-rose-500' : 'text-amber-500')} />
            <h4 className="txt text-[13px] font-semibold">Recent Sentiment</h4>
          </div>
          <StatusBadge label={data.recentSentiment} variant={data.recentSentiment === 'Positive' ? 'success' : data.recentSentiment === 'Negative' ? 'danger' : 'warning'} />
        </div>
      )}
      
      {data.preferredCommunicationStyle && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <MessageSquare className="h-4 w-4 text-sky-500" />
            <h4 className="txt text-[13px] font-semibold">Preferred Comms</h4>
          </div>
          <p className="txt-muted text-[12.5px] leading-relaxed">{data.preferredCommunicationStyle}</p>
        </div>
      )}

      {(data.nextBestAction || data.suggestedNextAction) && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <Map className="h-4 w-4 text-sky-500" />
            <h4 className="txt text-[13px] font-semibold">Next Best Action</h4>
          </div>
          <p className="txt-muted text-[12.5px] leading-relaxed">{data.nextBestAction || data.suggestedNextAction}</p>
        </div>
      )}

      {data.suggestedFollowUp && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <Lightbulb className="h-4 w-4 text-amber-500" />
            <h4 className="txt text-[13px] font-semibold">Suggested Follow-up</h4>
          </div>
          <p className="txt-muted text-[12.5px] leading-relaxed">{data.suggestedFollowUp}</p>
        </div>
      )}
      
      {data.stakeholdersToEngage && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <Users className="h-4 w-4 text-violet-500" />
            <h4 className="txt text-[13px] font-semibold">Stakeholders to Engage</h4>
          </div>
          <p className="txt-muted text-[12.5px] leading-relaxed">{data.stakeholdersToEngage}</p>
        </div>
      )}
      
      {data.missingInformation && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <h4 className="txt text-[13px] font-semibold">Missing Information</h4>
          </div>
          <p className="txt-muted text-[12.5px] leading-relaxed">{data.missingInformation}</p>
        </div>
      )}
      
      {data.riskLevel && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-rose-500" />
            <h4 className="txt text-[13px] font-semibold">Risk Level</h4>
          </div>
          <div className="mb-1">
             <StatusBadge label={data.riskLevel} variant={getRiskVariant(data.riskLevel)} />
          </div>
        </div>
      )}

      {(data.executiveSummary || data.contactSummary) && (
        <div className="surface-2 rounded-xl border border-[var(--border)] p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            <h4 className="txt text-[13px] font-semibold">Executive Brief</h4>
          </div>
          <p className="txt-muted text-[12.5px] leading-relaxed">{data.executiveSummary || data.contactSummary}</p>
        </div>
      )}

    </div>
  );
}
