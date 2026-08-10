import { AlertTriangle, Building2, Info, Target } from 'lucide-react';
import StatusBadge, { type BadgeVariant } from '@/components/crm/shared/StatusBadge';
import ScoreMeter, { toneForScore } from '@/components/crm/ai/shared/ScoreMeter';
import { formatCurrency, formatDate } from '@/features/ai/shared/format';
import type { AiInsightReport, DealHealth } from '@/features/ai/insights/types';

/* ============================================================
   AI EXECUTIVE SUMMARY
   The first thing rendered after generation: enough for an
   executive to understand the account in a few seconds before
   any detailed section is opened.
   ============================================================ */

const HEALTH_VARIANT: Record<DealHealth, BadgeVariant> = {
  Healthy: 'success',
  Watch: 'warning',
  'At Risk': 'danger',
  Critical: 'danger',
};

interface AiExecutiveSummaryProps {
  report: AiInsightReport;
  /** Explains which account an analytical query resolved to, when relevant. */
  focusNote: string | null;
}

export default function AiExecutiveSummary({ report, focusNote }: AiExecutiveSummaryProps) {
  const { customerSummary: customer, relationshipScore, salesHealth, confidence } = report;

  return (
    <section className="surface bd rounded-2xl border p-4 sm:p-5" aria-labelledby="ai-executive-summary">
      {/* ── Heading ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-600">
            <Building2 className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h2 id="ai-executive-summary" className="font-display txt text-[18px] font-extrabold leading-tight">
              {report.subject}
            </h2>
            <p className="txt-muted mt-1 text-[13px] leading-relaxed">{report.headline}</p>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <StatusBadge label={customer.industry} variant="neutral" />
          <StatusBadge label={salesHealth.dealHealth} variant={HEALTH_VARIANT[salesHealth.dealHealth]} />
        </div>
      </div>

      {focusNote && (
        <p className="surface-2 bd txt-muted mt-3.5 flex items-start gap-2 rounded-xl border p-3 text-[12.5px] leading-relaxed">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
          {focusNote}
        </p>
      )}

      {/* ── Headline metrics ── */}
      <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="surface-2 bd rounded-xl border p-3.5">
          <dt className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Opportunity Value</dt>
          <dd className="font-display txt mt-1.5 text-[22px] font-extrabold leading-none">
            {formatCurrency(customer.opportunityValue)}
          </dd>
          <p className="txt-faint mt-1.5 text-[11.5px] font-medium">
            Closes {formatDate(customer.expectedCloseDate)}
          </p>
        </div>

        <div className="surface-2 bd rounded-xl border p-3.5">
          <dt className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Current Stage</dt>
          <dd className="font-display txt mt-1.5 text-[16px] font-extrabold leading-tight">
            {report.pipelinePosition.currentStage}
          </dd>
          <p className="txt-faint mt-1.5 text-[11.5px] font-medium">
            {salesHealth.daysInStage} days in stage · {salesHealth.momentum}
          </p>
        </div>

        <div className="surface-2 bd rounded-xl border p-3.5">
          <dt className="txt-muted text-[11px] font-semibold uppercase tracking-wider">Relationship</dt>
          <dd className="mt-1.5">
            <ScoreMeter
              value={relationshipScore.score}
              label="Relationship score"
              caption={relationshipScore.tier}
              tone={toneForScore(relationshipScore.score)}
              size="lg"
              hideLabel
            />
          </dd>
          <p className="font-display txt mt-1 text-[16px] font-extrabold leading-none">
            {relationshipScore.score}
            <span className="txt-faint text-[12px] font-bold">/100 · {relationshipScore.tier}</span>
          </p>
        </div>

        <div className="surface-2 bd rounded-xl border p-3.5">
          <dt className="txt-muted text-[11px] font-semibold uppercase tracking-wider">AI Confidence</dt>
          <dd className="mt-1.5">
            <ScoreMeter
              value={confidence.score}
              label="AI confidence"
              caption={confidence.tier}
              tone={toneForScore(confidence.score)}
              size="lg"
              hideLabel
            />
          </dd>
          <p className="font-display txt mt-1 text-[16px] font-extrabold leading-none">
            {confidence.score}%
            <span className="txt-faint text-[12px] font-bold"> · {confidence.tier}</span>
          </p>
        </div>
      </dl>

      {/* ── Primary recommendation and top risk ── */}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div
          className="rounded-xl border p-3.5"
          style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}
        >
          <p
            className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider"
            style={{ color: 'var(--accent)' }}
          >
            <Target className="h-3.5 w-3.5" aria-hidden="true" />
            Primary recommendation
          </p>
          <p className="txt mt-1.5 text-[13.5px] font-semibold leading-snug">
            {report.primaryRecommendation}
          </p>
        </div>

        <div className="surface-2 bd rounded-xl border p-3.5">
          <p className="txt-muted flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
            Top risk
          </p>
          <p className="txt mt-1.5 text-[13.5px] font-semibold leading-snug">{report.topRisk}</p>
        </div>
      </div>
    </section>
  );
}
