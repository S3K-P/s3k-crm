'use client';

import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  ClipboardList,
  FileText,
  Gauge,
  Heart,
  Info,
  Lightbulb,
  Mail,
  MessageSquare,
  Phone,
  Route,
  Target,
  TrendingUp,
  Users,
  Zap,
} from 'lucide-react';
import ActivityItem, { type ActivityEntry } from '@/components/crm/cards/ActivityItem';
import StatusBadge, { type BadgeVariant } from '@/components/crm/shared/StatusBadge';
import CopyButton from '@/components/crm/ai/shared/CopyButton';
import InsightSection from '@/components/crm/ai/shared/InsightSection';
import ScoreMeter, { toneForScore } from '@/components/crm/ai/shared/ScoreMeter';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import { cn } from '@/lib/utils';
import { formatCurrency, formatDate, initials } from '@/features/ai/shared/format';
import type {
  ActivityRecord,
  AiInsightReport,
  DealHealth,
} from '@/features/ai/insights/types';
import {
  ACTIVITY_ICONS,
  PRIORITY_VARIANT,
  SEVERITY_VARIANT,
  STRENGTH_VARIANT,
  agendaToText,
  callScriptToText,
  emailToText,
  takeawaysToText,
} from './report-helpers';

/* ============================================================
   AI INSIGHTS REPORT
   Renders every generated intelligence category. Each section
   uses the information-design pattern that suits it rather
   than a uniform block of text.
   ============================================================ */

const HEALTH_VARIANT: Record<DealHealth, BadgeVariant> = {
  Healthy: 'success',
  Watch: 'warning',
  'At Risk': 'danger',
  Critical: 'danger',
};

/* ---- Small building blocks ---- */

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="txt-faint text-[11px] font-semibold uppercase tracking-wider">{label}</dt>
      <dd className="txt mt-0.5 text-[13px] font-medium">{value}</dd>
    </div>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="surface-2 bd rounded-xl border p-3">
      <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">{label}</p>
      <p className="font-display txt mt-1 text-[16px] font-extrabold leading-tight">{value}</p>
      {note && <p className="txt-muted mt-0.5 text-[11.5px]">{note}</p>}
    </div>
  );
}

function toActivityEntry(activity: ActivityRecord): ActivityEntry {
  const config = ACTIVITY_ICONS[activity.type];
  return {
    id: activity.id,
    icon: config.icon,
    iconGradient: config.gradient,
    title: activity.title,
    detail: activity.detail,
    timestamp: formatDate(activity.date),
  };
}

/* ---- Report ---- */

interface AiInsightsReportProps {
  report: AiInsightReport;
}

export default function AiInsightsReport({ report }: AiInsightsReportProps) {
  const {
    customerSummary: customer,
    relationshipScore,
    buyingSignals,
    salesHealth,
    pipelinePosition,
    risks,
    activities,
    communication,
    decisionMakers,
    opportunities,
    followUps,
    suggestedEmail,
    callScript,
    meetingAgenda,
    confidence,
    importantNotes,
    keyTakeaways,
  } = report;

  const currentStageIndex = pipelinePosition.stageOrder.indexOf(pipelinePosition.currentStage);

  return (
    <div className="space-y-4">
      {/* ── Recommended follow-ups — the strongest actionable block ── */}
      <InsightSection
        icon={Zap}
        title="Recommended Follow-ups"
        summary={`${followUps.length} prioritised actions with owner, timing and target outcome`}
        meta={<StatusBadge label={`${followUps.filter(f => f.priority === 'Critical').length} critical`} variant="danger" />}
      >
        <ol className="space-y-2.5">
          {followUps.map((followUp, index) => (
            <li
              key={followUp.id}
              className="surface-2 bd rounded-xl border p-3.5"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2.5">
                  <span
                    className="font-display grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-bold text-white"
                    style={{ background: 'var(--accent)' }}
                    aria-hidden="true"
                  >
                    {index + 1}
                  </span>
                  <p className="txt min-w-0 text-[13.5px] font-semibold leading-snug">
                    {followUp.action}
                  </p>
                </div>
                <StatusBadge label={followUp.priority} variant={PRIORITY_VARIANT[followUp.priority]} />
              </div>

              <dl className="mt-2.5 grid gap-2.5 pl-[34px] sm:grid-cols-2">
                <Field label="Owner" value={followUp.owner} />
                <Field label="Timing" value={followUp.timing} />
                <Field label="Why now" value={<span className="txt-muted font-normal">{followUp.reason}</span>} />
                <Field label="Expected outcome" value={<span className="txt-muted font-normal">{followUp.expectedOutcome}</span>} />
              </dl>
            </li>
          ))}
        </ol>
      </InsightSection>

      {/* ── Two-column intelligence grid ── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Customer summary */}
        <InsightSection
          icon={FileText}
          title="Customer Summary"
          summary={`${customer.primaryContact} · ${customer.contactTitle}`}
        >
          <dl className="grid gap-3 sm:grid-cols-2">
            <Field label="Company" value={customer.company} />
            <Field label="Industry" value={customer.industry} />
            <Field label="Primary contact" value={customer.primaryContact} />
            <Field label="Contact title" value={customer.contactTitle} />
            <Field label="Relationship stage" value={customer.relationshipStage} />
            <Field label="Account owner" value={customer.accountOwner} />
            <Field label="Last interaction" value={formatDate(customer.lastInteraction)} />
            <Field label="Expected close" value={formatDate(customer.expectedCloseDate)} />
            <Field label="Opportunity" value={customer.opportunity} />
            <Field label="Opportunity value" value={formatCurrency(customer.opportunityValue)} />
          </dl>
          <p className="bd txt-muted mt-3.5 border-t pt-3.5 text-[13px] leading-relaxed">
            {customer.narrative}
          </p>
        </InsightSection>

        {/* Relationship score */}
        <InsightSection
          icon={Heart}
          title="Relationship Score"
          summary={`${relationshipScore.score}/100 — ${relationshipScore.tier}`}
          meta={<StatusBadge label={relationshipScore.tier} variant={relationshipScore.score >= 70 ? 'success' : relationshipScore.score >= 50 ? 'warning' : 'danger'} />}
        >
          <ScoreMeter
            value={relationshipScore.score}
            label="Overall relationship"
            caption={relationshipScore.tier}
            tone={toneForScore(relationshipScore.score)}
            size="lg"
          />
          <p className="txt-muted mt-3 text-[13px] leading-relaxed">{relationshipScore.rationale}</p>

          <div className="bd mt-3.5 space-y-3 border-t pt-3.5">
            {relationshipScore.factors.map(factor => (
              <div key={factor.label}>
                <ScoreMeter
                  value={factor.value}
                  label={factor.label}
                  tone={toneForScore(factor.value)}
                  size="sm"
                />
                <p className="txt-faint mt-1 text-[11.5px]">{factor.note}</p>
              </div>
            ))}
          </div>
        </InsightSection>

        {/* Buying signals */}
        <InsightSection
          icon={TrendingUp}
          title="Buying Signals"
          summary={`${buyingSignals.filter(s => s.strength === 'Strong').length} strong signals detected`}
          meta={<StatusBadge label={`${buyingSignals.length}`} variant="neutral" />}
        >
          <ul className="space-y-2.5">
            {buyingSignals.map(signal => (
              <li key={signal.id} className="surface-2 bd rounded-xl border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="txt min-w-0 text-[13px] font-semibold leading-snug">{signal.signal}</p>
                  <StatusBadge label={signal.strength} variant={STRENGTH_VARIANT[signal.strength]} />
                </div>
                <p className="txt-muted mt-1 text-[12.5px] leading-relaxed">{signal.explanation}</p>
                <p className="txt-faint mt-1.5 text-[11px] font-medium">{formatDate(signal.date)}</p>
              </li>
            ))}
          </ul>
        </InsightSection>

        {/* Sales health */}
        <InsightSection
          icon={Gauge}
          title="Sales Health"
          summary={`${salesHealth.dealHealth} · ${salesHealth.momentum} momentum`}
          meta={<StatusBadge label={salesHealth.dealHealth} variant={HEALTH_VARIANT[salesHealth.dealHealth]} />}
        >
          <div className="grid gap-2.5 sm:grid-cols-2">
            <Metric label="Win probability" value={`${salesHealth.winProbability}%`} />
            <Metric label="Deal momentum" value={salesHealth.momentum} />
            <Metric label="Days in stage" value={`${salesHealth.daysInStage} days`} note={`Segment average ${pipelinePosition.averageStageDays}`} />
            <Metric label="Target close" value={formatDate(salesHealth.targetCloseDate)} />
          </div>
          <div className="mt-3">
            <ScoreMeter
              value={salesHealth.winProbability}
              label="Win probability"
              tone={toneForScore(salesHealth.winProbability)}
            />
          </div>
          <div className="bd mt-3.5 border-t pt-3.5">
            <Field label="Next milestone" value={salesHealth.nextMilestone} />
            <p className="txt-muted mt-2 text-[12.5px] leading-relaxed">{salesHealth.note}</p>
          </div>
        </InsightSection>

        {/* Pipeline position */}
        <InsightSection
          icon={Route}
          title="Pipeline Position"
          summary={`${pipelinePosition.currentStage} — ${pipelinePosition.pipelineHealth}`}
        >
          <ol className="flex items-stretch gap-1" aria-label="Pipeline stage progress">
            {pipelinePosition.stageOrder.map((stage, index) => {
              const passed = index < currentStageIndex;
              const current = index === currentStageIndex;
              return (
                <li key={stage} className="min-w-0 flex-1">
                  <div
                    className={cn('h-1.5 rounded-full', !passed && !current && 'opacity-100')}
                    style={{
                      background: passed || current ? 'var(--accent)' : 'var(--border)',
                      opacity: passed ? 0.55 : 1,
                    }}
                  />
                  <p
                    className={cn(
                      'mt-1.5 truncate text-[10.5px] font-semibold',
                      current ? 'txt' : 'txt-faint',
                    )}
                    title={stage}
                  >
                    {current && <span className="sr-only">Current stage: </span>}
                    {stage}
                  </p>
                </li>
              );
            })}
          </ol>
          <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
            <Metric label="Pipeline health" value={pipelinePosition.pipelineHealth} />
            <Metric label="Avg. stage duration" value={`${pipelinePosition.averageStageDays} days`} />
          </div>
          <p className="txt-muted mt-3 text-[12.5px] leading-relaxed">{pipelinePosition.note}</p>
        </InsightSection>

        {/* Risk indicators */}
        <InsightSection
          icon={AlertTriangle}
          title="Risk Indicators"
          summary={`${risks.length} indicators — highest severity ${risks[0]?.severity ?? 'Low'}`}
          meta={<StatusBadge label={risks[0]?.severity ?? 'Low'} variant={SEVERITY_VARIANT[risks[0]?.severity ?? 'Low']} />}
        >
          <ul className="space-y-2.5">
            {risks.map(risk => (
              <li key={risk.id} className="surface-2 bd rounded-xl border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="txt min-w-0 text-[13px] font-semibold leading-snug">{risk.risk}</p>
                  <StatusBadge label={risk.severity} variant={SEVERITY_VARIANT[risk.severity]} />
                </div>
                <dl className="mt-2 space-y-1.5">
                  <div>
                    <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Evidence</dt>
                    <dd className="txt-muted text-[12.5px] leading-relaxed">{risk.evidence}</dd>
                  </div>
                  <div>
                    <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Potential impact</dt>
                    <dd className="txt-muted text-[12.5px] leading-relaxed">{risk.impact}</dd>
                  </div>
                  <div>
                    <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Suggested mitigation</dt>
                    <dd className="txt text-[12.5px] font-medium leading-relaxed">{risk.mitigation}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </InsightSection>

        {/* Recent activities */}
        <InsightSection
          icon={Activity}
          title="Recent Activities"
          summary={`${activities.length} interactions in the current cycle`}
        >
          {activities.length === 0 ? (
            <AiEmptyState
              icon={Activity}
              title="No activity logged"
              description="Nothing has been recorded against this account in the current cycle."
              size="inline"
            />
          ) : (
            <div>
              {activities.map((activity, index) => (
                <ActivityItem
                  key={activity.id}
                  activity={toActivityEntry(activity)}
                  showConnector={index < activities.length - 1}
                />
              ))}
            </div>
          )}
        </InsightSection>

        {/* Communication summary */}
        <InsightSection
          icon={MessageSquare}
          title="Communication Summary"
          summary={`${communication.engagementLevel} engagement · ${communication.sentiment} sentiment`}
          meta={
            <StatusBadge
              label={communication.sentiment}
              variant={
                communication.sentiment === 'Positive'
                  ? 'success'
                  : communication.sentiment === 'Negative'
                    ? 'danger'
                    : 'warning'
              }
            />
          }
        >
          <div className="grid gap-2.5 sm:grid-cols-2">
            <Metric label="Last communication" value={formatDate(communication.lastCommunication)} />
            <Metric label="Communication gap" value={`${communication.currentGapDays} days`} />
            <Metric label="Avg. response time" value={`${communication.averageResponseHours}h`} />
            <Metric label="Engagement level" value={communication.engagementLevel} />
          </div>
          <p className="txt-muted mt-3 text-[12.5px] leading-relaxed">
            <span className="txt font-semibold">Response trend: </span>
            {communication.responseTrend}
          </p>
          <div className="bd mt-3.5 border-t pt-3.5">
            <p className="txt-faint mb-1.5 text-[10.5px] font-bold uppercase tracking-wider">
              Open questions
            </p>
            <ul className="space-y-1.5">
              {communication.openQuestions.map(question => (
                <li key={question} className="txt-muted flex gap-2 text-[12.5px] leading-relaxed">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full" style={{ background: 'var(--accent)' }} aria-hidden="true" />
                  {question}
                </li>
              ))}
            </ul>
          </div>
        </InsightSection>

        {/* Decision makers */}
        <InsightSection
          icon={Users}
          title="Decision Makers"
          summary={`${decisionMakers.length} stakeholders mapped`}
        >
          <ul className="space-y-2.5">
            {decisionMakers.map(person => (
              <li key={person.id} className="surface-2 bd rounded-xl border p-3">
                <div className="flex items-start gap-2.5">
                  <span
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-[11px] font-bold text-white"
                    aria-hidden="true"
                  >
                    {initials(person.name)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <p className="txt text-[13px] font-semibold">{person.name}</p>
                      <StatusBadge label={person.buyingRole} variant={person.buyingRole === 'Blocker' ? 'danger' : 'accent'} />
                    </div>
                    <p className="txt-muted text-[12px]">{person.role}</p>
                    <div className="txt-faint mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] font-medium">
                      <span>Influence: {person.influence}</span>
                      <span>Engagement: {person.engagement}</span>
                      <span>Relationship: {person.relationship}</span>
                    </div>
                    <p className="txt-muted mt-1.5 text-[12.5px] leading-relaxed">
                      <span className="txt-faint font-semibold">Main concern: </span>
                      {person.keyConcern}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </InsightSection>

        {/* Sales opportunities */}
        <InsightSection
          icon={Target}
          title="Sales Opportunities"
          summary={`${opportunities.length} open opportunities · ${formatCurrency(opportunities.reduce((total, o) => total + o.value, 0))} total`}
        >
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse">
              <thead>
                <tr className="bd border-b">
                  <th scope="col" className="txt-faint px-1 py-2 text-left text-[10.5px] font-bold uppercase tracking-wider">Opportunity</th>
                  <th scope="col" className="txt-faint px-1 py-2 text-left text-[10.5px] font-bold uppercase tracking-wider">Stage</th>
                  <th scope="col" className="txt-faint px-1 py-2 text-right text-[10.5px] font-bold uppercase tracking-wider">Value</th>
                  <th scope="col" className="txt-faint px-1 py-2 text-center text-[10.5px] font-bold uppercase tracking-wider">Prob.</th>
                  <th scope="col" className="txt-faint px-1 py-2 text-left text-[10.5px] font-bold uppercase tracking-wider">Close</th>
                  <th scope="col" className="txt-faint px-1 py-2 text-left text-[10.5px] font-bold uppercase tracking-wider">Health</th>
                </tr>
              </thead>
              <tbody>
                {opportunities.map(opportunity => (
                  <tr key={opportunity.id} className="bd border-b last:border-b-0">
                    <td className="px-1 py-2.5">
                      <p className="txt text-[12.5px] font-semibold">{opportunity.name}</p>
                      <p className="txt-faint text-[11.5px]">{opportunity.nextMilestone}</p>
                    </td>
                    <td className="px-1 py-2.5"><StatusBadge label={opportunity.stage} variant="accent" /></td>
                    <td className="font-display txt px-1 py-2.5 text-right text-[12.5px] font-bold">{formatCurrency(opportunity.value)}</td>
                    <td className="txt-muted px-1 py-2.5 text-center text-[12.5px]">{opportunity.probability}%</td>
                    <td className="txt-muted px-1 py-2.5 text-[12px]">{formatDate(opportunity.expectedCloseDate)}</td>
                    <td className="px-1 py-2.5"><StatusBadge label={opportunity.health} variant={HEALTH_VARIANT[opportunity.health]} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </InsightSection>
      </div>

      {/* ── Suggested communications ── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <InsightSection
          icon={Mail}
          title="Suggested Email Draft"
          summary={suggestedEmail.subject}
          action={<CopyButton value={emailToText(suggestedEmail)} label="Email draft" showLabel />}
        >
          <div className="surface-2 bd rounded-xl border p-3.5">
            <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Subject</p>
            <p className="txt mt-0.5 text-[13px] font-semibold">{suggestedEmail.subject}</p>
            <div className="bd mt-3 border-t pt-3">
              <p className="txt-muted whitespace-pre-line text-[12.5px] leading-relaxed">
                {suggestedEmail.body}
              </p>
            </div>
          </div>
          <p className="txt-faint mt-2.5 text-[11.5px]">
            Draft only — nothing is sent from this screen.
          </p>
        </InsightSection>

        <InsightSection
          icon={Phone}
          title="Suggested Call Script"
          summary={`${callScript.length} sections from opening through to next step`}
          action={<CopyButton value={callScriptToText(callScript)} label="Call script" showLabel />}
        >
          <ol className="space-y-3">
            {callScript.map(section => (
              <li key={section.label}>
                <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">{section.label}</p>
                <ul className="mt-1 space-y-1">
                  {section.lines.map(line => (
                    <li key={line} className="txt-muted text-[12.5px] italic leading-relaxed">
                      {line}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </InsightSection>

        <InsightSection
          icon={CalendarClock}
          title="Suggested Meeting Agenda"
          summary={`${meetingAgenda.reduce((total, item) => total + item.minutes, 0)} minutes across ${meetingAgenda.length} topics`}
          action={<CopyButton value={agendaToText(meetingAgenda)} label="Meeting agenda" showLabel />}
        >
          <ol className="space-y-2.5">
            {meetingAgenda.map((item, index) => (
              <li key={item.topic} className="flex gap-2.5">
                <span
                  className="surface-2 bd font-display txt-muted grid h-6 w-6 shrink-0 place-items-center rounded-full border text-[11px] font-bold"
                  aria-hidden="true"
                >
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="txt text-[13px] font-semibold">{item.topic}</p>
                    <span className="txt-faint text-[11.5px] font-bold">{item.minutes} min</span>
                  </div>
                  <p className="txt-muted mt-0.5 text-[12.5px] leading-relaxed">{item.objective}</p>
                  <p className="txt-faint mt-0.5 text-[11.5px]">{item.participants}</p>
                </div>
              </li>
            ))}
          </ol>
        </InsightSection>

        {/* AI confidence */}
        <InsightSection
          icon={BadgeCheck}
          title="AI Confidence Score"
          summary={`${confidence.score}% — ${confidence.tier}`}
          meta={<StatusBadge label={confidence.tier} variant={confidence.score >= 80 ? 'success' : confidence.score >= 60 ? 'warning' : 'danger'} />}
        >
          <ScoreMeter
            value={confidence.score}
            label="Overall confidence"
            caption={confidence.tier}
            tone={toneForScore(confidence.score)}
            size="lg"
          />
          <div className="mt-3.5">
            <p className="txt-faint mb-1.5 text-[10.5px] font-bold uppercase tracking-wider">
              Supporting rationale
            </p>
            <ul className="space-y-1.5">
              {confidence.rationale.map(reason => (
                <li key={reason} className="txt-muted flex gap-2 text-[12.5px] leading-relaxed">
                  <BadgeCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden="true" />
                  {reason}
                </li>
              ))}
            </ul>
          </div>
          <div className="bd mt-3.5 border-t pt-3.5">
            <p className="txt-faint mb-1 text-[10.5px] font-bold uppercase tracking-wider">Where it is uncertain</p>
            <p className="txt-muted text-[12.5px] leading-relaxed">{confidence.uncertainty}</p>
          </div>
        </InsightSection>
      </div>

      {/* ── Key takeaways and notes ── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <InsightSection
          icon={Lightbulb}
          title="Key Takeaways"
          summary={`${keyTakeaways.length} points for the account review`}
          action={<CopyButton value={takeawaysToText(report.subject, keyTakeaways)} label="Key takeaways" showLabel />}
        >
          <ul className="space-y-2">
            {keyTakeaways.map(takeaway => (
              <li key={takeaway} className="txt flex gap-2.5 text-[13px] font-medium leading-relaxed">
                <span
                  className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: 'var(--accent)' }}
                  aria-hidden="true"
                />
                {takeaway}
              </li>
            ))}
          </ul>
        </InsightSection>

        <InsightSection
          icon={ClipboardList}
          title="Important Notes"
          summary="Review guidance before acting on generated content"
          defaultOpen
        >
          <ul className="space-y-2">
            {importantNotes.map(note => (
              <li key={note} className="txt-muted flex gap-2.5 text-[12.5px] leading-relaxed">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
                {note}
              </li>
            ))}
          </ul>
        </InsightSection>
      </div>
    </div>
  );
}
