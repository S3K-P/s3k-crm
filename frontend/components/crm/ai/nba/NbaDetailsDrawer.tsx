'use client';

import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BrainCircuit,
  Building2,
  CalendarClock,
  CheckCircle2,
  FileSignature,
  FileText,
  Mail,
  MessageCircle,
  Phone,
  RefreshCw,
  Shuffle,
  Swords,
  Target,
  UserRound,
  Users,
  Zap,
} from 'lucide-react';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import ActivityItem, { type ActivityEntry } from '@/components/crm/cards/ActivityItem';
import InsightSection from '@/components/crm/ai/shared/InsightSection';
import ScoreMeter, { toneForScore } from '@/components/crm/ai/shared/ScoreMeter';
import CopyButton from '@/components/crm/ai/shared/CopyButton';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import { ACTIVITY_ICONS } from '@/components/crm/ai/insights/report-helpers';
import {
  PRIORITY_VARIANT,
  PROPOSAL_VARIANT,
  RISK_VARIANT,
  SEVERITY_VARIANT,
  SOW_VARIANT,
  STATUS_VARIANT,
  agendaToText,
  callScriptToText,
  confidenceTone,
  emailToText,
} from './nba-helpers';
import { formatCurrency, formatDate, initials } from '@/features/ai/shared/format';
import type { NbaDetail, NbaRecord, TimelineEvent } from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA DETAILS DRAWER
   Opportunity intelligence for a single recommendation,
   organised into four areas rather than one endless list.
   Reuses the CRM's SlideDrawer, Tabs and timeline components.
   ============================================================ */

/* ---- Local building blocks ---- */

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">{label}</dt>
      <dd className="txt mt-0.5 break-words text-[12.5px] font-medium">{value}</dd>
    </div>
  );
}

function HeaderStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="surface-2 bd min-w-0 rounded-xl border px-3 py-2">
      <p className="txt-faint text-[10px] font-bold uppercase tracking-wider">{label}</p>
      <div className="txt mt-0.5 text-[13px] font-bold">{value}</div>
    </div>
  );
}

const TIMELINE_ICON_KEY: Record<TimelineEvent['kind'], keyof typeof ACTIVITY_ICONS> = {
  call: 'call',
  email: 'email',
  meeting: 'meeting',
  proposal: 'proposal',
  stage: 'stage',
  document: 'document',
  ai: 'task',
  task: 'task',
};

function toActivityEntry(event: TimelineEvent): ActivityEntry {
  const config = ACTIVITY_ICONS[TIMELINE_ICON_KEY[event.kind]];
  return {
    id: event.id,
    icon: config.icon,
    iconGradient: config.gradient,
    title: event.title,
    detail: event.detail,
    timestamp: formatDate(event.date),
  };
}

function DetailSkeleton() {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="surface bd rounded-2xl border p-4">
          <div className="h-3 w-40 rounded motion-safe:animate-pulse" style={{ background: 'var(--border)' }} />
          <div className="mt-3 space-y-2">
            <div className="h-2.5 w-full rounded motion-safe:animate-pulse" style={{ background: 'var(--border)' }} />
            <div className="h-2.5 w-4/5 rounded motion-safe:animate-pulse" style={{ background: 'var(--border)' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---- Drawer ---- */

interface NbaDetailsDrawerProps {
  open: boolean;
  record: NbaRecord | null;
  detail: NbaDetail | null;
  loading: boolean;
  regenerating: boolean;
  onClose: () => void;
  onMarkCompleted: (record: NbaRecord) => void;
  onRegenerate: (record: NbaRecord) => void;
}

export default function NbaDetailsDrawer({
  open,
  record,
  detail,
  loading,
  regenerating,
  onClose,
  onMarkCompleted,
  onRegenerate,
}: NbaDetailsDrawerProps) {
  if (!record) return null;

  const completed = record.status === 'Completed';

  /* ---- Tab content ---- */

  const overviewTab = detail && (
    <div className="space-y-3">
      {/* Next Best Action highlight */}
      <section
        className="rounded-2xl border p-4"
        style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p
            className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider"
            style={{ color: 'var(--accent)' }}
          >
            <Zap className="h-3.5 w-3.5" aria-hidden="true" />
            Next Best Action
          </p>
          <StatusBadge label={detail.highlight.priority} variant={PRIORITY_VARIANT[detail.highlight.priority]} />
        </div>

        <h3 className="txt font-display mt-2 text-[15px] font-extrabold leading-snug">
          {detail.highlight.action}
        </h3>

        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="Recommended timing" value={detail.highlight.timing} />
          <Field label="Owner" value={detail.highlight.owner} />
          <Field label="Why now" value={<span className="txt-muted font-normal">{detail.highlight.reason}</span>} />
          <Field label="Expected impact" value={<span className="txt-muted font-normal">{detail.highlight.expectedImpact}</span>} />
        </dl>

        <div className="mt-3">
          <ScoreMeter
            value={detail.highlight.confidence}
            label="AI confidence in this recommendation"
            tone={confidenceTone(detail.highlight.confidence)}
          />
        </div>
      </section>

      <InsightSection
        icon={Target}
        title="Opportunity Summary"
        summary={`${detail.opportunitySummary.stage} · ${formatCurrency(detail.opportunitySummary.dealSize)}`}
      >
        <dl className="grid gap-3 sm:grid-cols-2">
          <Field label="Opportunity" value={detail.opportunitySummary.name} />
          <Field label="Stage" value={detail.opportunitySummary.stage} />
          <Field label="Deal size" value={formatCurrency(detail.opportunitySummary.dealSize)} />
          <Field label="Win probability" value={`${detail.opportunitySummary.winProbability}%`} />
          <Field label="Expected close" value={formatDate(detail.opportunitySummary.expectedCloseDate)} />
          <Field label="Days in stage" value={`${detail.opportunitySummary.daysInStage} days`} />
          <Field label="Last activity" value={detail.opportunitySummary.lastActivity} />
          <Field label="Deal momentum" value={detail.opportunitySummary.momentum} />
          <Field label="Next milestone" value={detail.opportunitySummary.nextMilestone} />
        </dl>
      </InsightSection>

      <InsightSection
        icon={UserRound}
        title="Lead Summary"
        summary={`${detail.leadSummary.title} · ${detail.leadSummary.company}`}
      >
        <dl className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" value={detail.leadSummary.name} />
          <Field label="Company" value={detail.leadSummary.company} />
          <Field label="Role / title" value={detail.leadSummary.title} />
          <Field label="Owner" value={detail.leadSummary.owner} />
          <Field label="Email" value={detail.leadSummary.email} />
          <Field label="Phone" value={detail.leadSummary.phone} />
          <Field label="Lead source" value={detail.leadSummary.leadSource} />
          <Field label="Engagement level" value={detail.leadSummary.engagement} />
        </dl>
      </InsightSection>

      <InsightSection
        icon={BrainCircuit}
        title="AI Analysis"
        summary="Why this action was selected"
      >
        <p className="txt-muted text-[12.5px] leading-relaxed">{detail.aiAnalysis.rationale}</p>

        <div className="bd mt-3.5 border-t pt-3.5">
          <p className="txt-faint mb-2 text-[10.5px] font-bold uppercase tracking-wider">
            Evidence considered
          </p>
          <dl className="grid gap-2.5 sm:grid-cols-2">
            {detail.aiAnalysis.evidence.map(item => (
              <Field key={item.label} label={item.label} value={<span className="txt-muted font-normal">{item.value}</span>} />
            ))}
          </dl>
        </div>

        <div className="bd mt-3.5 border-t pt-3.5">
          <p className="txt-faint mb-1 text-[10.5px] font-bold uppercase tracking-wider">
            Where it is uncertain
          </p>
          <p className="txt-muted text-[12.5px] leading-relaxed">{detail.aiAnalysis.uncertainty}</p>
        </div>
      </InsightSection>

      <InsightSection
        icon={AlertTriangle}
        title="Deal Risks"
        summary={`${detail.risks.length} indicators — highest ${detail.risks[0]?.severity ?? 'Low'}`}
        meta={<StatusBadge label={detail.risks[0]?.severity ?? 'Low'} variant={SEVERITY_VARIANT[detail.risks[0]?.severity ?? 'Low']} />}
      >
        <ul className="space-y-2.5">
          {detail.risks.map(risk => (
            <li key={risk.id} className="surface-2 bd rounded-xl border p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="txt min-w-0 text-[12.5px] font-semibold leading-snug">{risk.risk}</p>
                <StatusBadge label={risk.severity} variant={SEVERITY_VARIANT[risk.severity]} />
              </div>
              <p className="txt-muted mt-1.5 text-[12px] leading-relaxed">
                <span className="txt-faint font-semibold">Evidence: </span>{risk.evidence}
              </p>
              <p className="txt-muted mt-1 text-[12px] leading-relaxed">
                <span className="txt-faint font-semibold">Impact: </span>{risk.impact}
              </p>
              <p className="txt mt-1 text-[12px] font-medium leading-relaxed">
                <span className="txt-faint font-semibold">Mitigation: </span>{risk.mitigation}
              </p>
            </li>
          ))}
        </ul>
      </InsightSection>
    </div>
  );

  const engagementTab = detail && (
    <div className="space-y-3">
      <InsightSection
        icon={Users}
        title="Past Meetings"
        summary={`${detail.meetings.length} meetings logged`}
      >
        {detail.meetings.length === 0 ? (
          <AiEmptyState icon={Users} title="No meetings logged" description="No meetings have been recorded against this opportunity." size="inline" />
        ) : (
          <ul className="space-y-2.5">
            {detail.meetings.map(meeting => (
              <li key={meeting.id} className="surface-2 bd rounded-xl border p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="txt text-[12.5px] font-semibold">{meeting.title}</p>
                  <span className="txt-faint text-[11.5px] font-medium">{formatDate(meeting.date)}</span>
                </div>
                <p className="txt-faint mt-1 text-[11.5px]">{meeting.participants.join(', ')}</p>
                <p className="txt-muted mt-1.5 text-[12px] leading-relaxed">{meeting.summary}</p>
                <p className="txt-muted mt-1 text-[12px]">
                  <span className="txt-faint font-semibold">Outcome: </span>{meeting.outcome}
                </p>
                <p className="txt mt-1 text-[12px] font-medium">
                  <span className="txt-faint font-semibold">Commitment: </span>{meeting.followUpCommitment}
                </p>
              </li>
            ))}
          </ul>
        )}
      </InsightSection>

      <InsightSection
        icon={Mail}
        title="Email History"
        summary={`${detail.emails.length} emails · ${detail.emails.filter(e => e.engagement === 'No Response').length} without reply`}
      >
        {detail.emails.length === 0 ? (
          <AiEmptyState icon={Mail} title="No email history" description="No correspondence has been recorded for this opportunity." size="inline" />
        ) : (
          <ul className="space-y-2">
            {detail.emails.map(email => (
              <li key={email.id} className="surface-2 bd rounded-xl border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="txt min-w-0 text-[12.5px] font-semibold">{email.subject}</p>
                  <StatusBadge
                    label={email.engagement}
                    variant={
                      email.engagement === 'Replied' ? 'success'
                        : email.engagement === 'No Response' ? 'danger'
                          : 'accent'
                    }
                  />
                </div>
                <p className="txt-faint mt-1 text-[11.5px] font-medium">
                  {email.direction} · {formatDate(email.date)}
                </p>
                <p className="txt-muted mt-1 text-[12px] leading-relaxed">{email.aiSummary}</p>
              </li>
            ))}
          </ul>
        )}
      </InsightSection>

      <InsightSection
        icon={Phone}
        title="Call History"
        summary={`${detail.calls.length} calls logged`}
      >
        <ul className="space-y-2.5">
          {detail.calls.map(call => (
            <li key={call.id} className="surface-2 bd rounded-xl border p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="txt text-[12.5px] font-semibold">{call.outcome}</p>
                <span className="txt-faint text-[11.5px] font-medium">
                  {formatDate(call.date)} · {call.durationMinutes} min
                </span>
              </div>
              <p className="txt-faint mt-0.5 text-[11.5px]">{call.salesperson}</p>
              <p className="txt-muted mt-1.5 text-[12px] leading-relaxed">{call.summary}</p>
              <p className="txt-muted mt-1 text-[12px]">
                <span className="txt-faint font-semibold">Objection: </span>{call.objection}
              </p>
              <p className="txt mt-1 text-[12px] font-medium">
                <span className="txt-faint font-semibold">Follow-up: </span>{call.followUpAction}
              </p>
            </li>
          ))}
        </ul>
      </InsightSection>

      <InsightSection
        icon={Users}
        title="Decision Makers"
        summary={`${detail.stakeholders.length} stakeholders mapped`}
      >
        <ul className="space-y-2.5">
          {detail.stakeholders.map(person => (
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
                    <p className="txt text-[12.5px] font-semibold">{person.name}</p>
                    <StatusBadge label={person.buyingRole} variant={person.buyingRole === 'Blocker' ? 'danger' : 'accent'} />
                  </div>
                  <p className="txt-muted text-[12px]">{person.role}</p>
                  <div className="txt-faint mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] font-medium">
                    <span>Influence: {person.influence}</span>
                    <span>Engagement: {person.engagement}</span>
                    <span>Relationship: {person.relationship}</span>
                  </div>
                  <p className="txt-muted mt-1.5 text-[12px] leading-relaxed">
                    <span className="txt-faint font-semibold">Key concern: </span>{person.keyConcern}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </InsightSection>

      <InsightSection
        icon={AlertTriangle}
        title="Pain Points"
        summary={`${detail.painPoints.length} operational drivers identified`}
      >
        <ul className="space-y-2">
          {detail.painPoints.map(point => (
            <li key={point} className="txt-muted flex gap-2.5 text-[12.5px] leading-relaxed">
              <span
                className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: 'var(--accent)' }}
                aria-hidden="true"
              />
              {point}
            </li>
          ))}
        </ul>
      </InsightSection>

      <InsightSection
        icon={Activity}
        title="Activity Timeline"
        summary={`${detail.timeline.length} events, most recent first`}
      >
        <div>
          {detail.timeline.map((event, index) => (
            <ActivityItem
              key={event.id}
              activity={toActivityEntry(event)}
              showConnector={index < detail.timeline.length - 1}
            />
          ))}
        </div>
      </InsightSection>
    </div>
  );

  const recommendationsTab = detail && (
    <div className="space-y-3">
      <InsightSection
        icon={Mail}
        title="Suggested Email"
        summary={detail.suggestedEmail.subject}
        action={<CopyButton value={emailToText(detail.suggestedEmail)} label="Email draft" />}
      >
        <div className="surface-2 bd rounded-xl border p-3.5">
          <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Subject</p>
          <p className="txt mt-0.5 text-[12.5px] font-semibold">{detail.suggestedEmail.subject}</p>
          <div className="bd mt-2.5 border-t pt-2.5">
            <p className="txt-muted whitespace-pre-line text-[12px] leading-relaxed">
              {detail.suggestedEmail.body}
            </p>
          </div>
        </div>
      </InsightSection>

      <InsightSection
        icon={MessageCircle}
        title="Suggested WhatsApp"
        summary="Short-form follow-up message"
        action={<CopyButton value={detail.suggestedWhatsapp} label="WhatsApp message" />}
      >
        <p
          className="txt whitespace-pre-line rounded-xl px-3.5 py-3 text-[12.5px] leading-relaxed"
          style={{ background: 'var(--accent-soft)' }}
        >
          {detail.suggestedWhatsapp}
        </p>
      </InsightSection>

      <InsightSection
        icon={Phone}
        title="Call Script"
        summary={`${detail.callScript.length} sections`}
        action={<CopyButton value={callScriptToText(detail.callScript)} label="Call script" />}
        defaultOpen={false}
      >
        <ol className="space-y-3">
          {detail.callScript.map(section => (
            <li key={section.label}>
              <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">{section.label}</p>
              <ul className="mt-1 space-y-1">
                {section.lines.map(line => (
                  <li key={line} className="txt-muted text-[12px] italic leading-relaxed">{line}</li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </InsightSection>

      <InsightSection
        icon={CalendarClock}
        title="Meeting Agenda"
        summary={`${detail.meetingAgenda.reduce((total, item) => total + item.minutes, 0)} minutes`}
        action={<CopyButton value={agendaToText(detail.meetingAgenda)} label="Meeting agenda" />}
        defaultOpen={false}
      >
        <ol className="space-y-2.5">
          {detail.meetingAgenda.map((item, index) => (
            <li key={item.topic} className="flex gap-2.5">
              <span
                className="surface-2 bd font-display txt-muted grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10.5px] font-bold"
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="txt text-[12.5px] font-semibold">{item.topic}</p>
                  <span className="txt-faint text-[11px] font-bold">{item.minutes} min</span>
                </div>
                <p className="txt-muted mt-0.5 text-[12px] leading-relaxed">{item.objective}</p>
                <p className="txt-faint mt-0.5 text-[11.5px]">{item.participants}</p>
              </div>
            </li>
          ))}
        </ol>
      </InsightSection>

      <InsightSection
        icon={Shuffle}
        title="Cross-Sell Opportunities"
        summary={`${detail.crossSell.length} adjacent plays identified`}
      >
        {detail.crossSell.length === 0 ? (
          <AiEmptyState icon={Shuffle} title="No cross-sell identified" description="Nothing in the current engagement suggests an adjacent offering yet." size="inline" />
        ) : (
          <ul className="space-y-2.5">
            {detail.crossSell.map(play => (
              <li key={play.offering} className="surface-2 bd rounded-xl border p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="txt text-[12.5px] font-semibold">{play.offering}</p>
                  <span className="font-display txt text-[12.5px] font-bold">{formatCurrency(play.estimatedValue)}</span>
                </div>
                <div className="mt-1"><StatusBadge label={`${play.relevance} relevance`} variant={play.relevance === 'High' ? 'success' : 'neutral'} /></div>
                <p className="txt-muted mt-1.5 text-[12px] leading-relaxed">{play.rationale}</p>
                <p className="txt mt-1 text-[12px] font-medium leading-relaxed">
                  <span className="txt-faint font-semibold">Positioning: </span>{play.positioning}
                </p>
              </li>
            ))}
          </ul>
        )}
      </InsightSection>

      <InsightSection
        icon={ArrowUpRight}
        title="Upsell Opportunities"
        summary={detail.upsell.length > 0 ? `${detail.upsell.length} expansion plays identified` : 'None identified at this deal size'}
      >
        {detail.upsell.length === 0 ? (
          <AiEmptyState
            icon={ArrowUpRight}
            title="No upsell identified"
            description="Expansion plays are surfaced once the opportunity passes the segment value threshold."
            size="inline"
          />
        ) : (
          <ul className="space-y-2.5">
            {detail.upsell.map(play => (
              <li key={play.offering} className="surface-2 bd rounded-xl border p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="txt text-[12.5px] font-semibold">{play.offering}</p>
                  <span className="font-display txt text-[12.5px] font-bold">{formatCurrency(play.estimatedValue)}</span>
                </div>
                <div className="mt-1"><StatusBadge label={`${play.relevance} relevance`} variant={play.relevance === 'High' ? 'success' : 'neutral'} /></div>
                <p className="txt-muted mt-1.5 text-[12px] leading-relaxed">{play.rationale}</p>
                <p className="txt mt-1 text-[12px] font-medium leading-relaxed">
                  <span className="txt-faint font-semibold">Positioning: </span>{play.positioning}
                </p>
              </li>
            ))}
          </ul>
        )}
      </InsightSection>
    </div>
  );

  const dealTab = detail && (
    <div className="space-y-3">
      <InsightSection
        icon={FileSignature}
        title="Proposal Status"
        summary={`${detail.proposal.status} · ${detail.proposal.version}`}
        meta={<StatusBadge label={detail.proposal.status} variant={PROPOSAL_VARIANT[detail.proposal.status]} />}
      >
        <dl className="grid gap-3 sm:grid-cols-2">
          <Field label="Status" value={detail.proposal.status} />
          <Field label="Version" value={detail.proposal.version} />
          <Field label="Sent on" value={detail.proposal.sentOn ? formatDate(detail.proposal.sentOn) : 'Not issued'} />
          <Field label="Last viewed" value={detail.proposal.lastViewed ? formatDate(detail.proposal.lastViewed) : 'Not viewed'} />
          <Field label="Proposal value" value={formatCurrency(detail.proposal.value)} />
        </dl>
        <p className="txt-muted mt-3 text-[12px] leading-relaxed">{detail.proposal.note}</p>
      </InsightSection>

      <InsightSection
        icon={FileText}
        title="Statement of Work"
        summary={detail.sow.status}
        meta={<StatusBadge label={detail.sow.status} variant={SOW_VARIANT[detail.sow.status]} />}
      >
        <dl className="grid gap-3 sm:grid-cols-2">
          <Field label="Status" value={detail.sow.status} />
          <Field label="Owner" value={detail.sow.owner} />
          <Field label="Target date" value={detail.sow.targetDate ? formatDate(detail.sow.targetDate) : 'Not set'} />
        </dl>
        <p className="txt-muted mt-3 text-[12px] leading-relaxed">{detail.sow.note}</p>
      </InsightSection>

      <InsightSection
        icon={Swords}
        title="Competitive Notes"
        summary={`${detail.competitiveNotes.length} competitive positions tracked`}
      >
        <ul className="space-y-2.5">
          {detail.competitiveNotes.map(note => (
            <li key={note.competitor} className="surface-2 bd rounded-xl border p-3">
              <p className="txt text-[12.5px] font-semibold">{note.competitor}</p>
              <p className="txt-muted mt-1.5 text-[12px] leading-relaxed">
                <span className="txt-faint font-semibold">Customer concern: </span>{note.customerConcern}
              </p>
              <p className="txt-muted mt-1 text-[12px] leading-relaxed">
                <span className="txt-faint font-semibold">Their strength: </span>{note.competitorStrength}
              </p>
              <p className="txt mt-1 text-[12px] font-medium leading-relaxed">
                <span className="txt-faint font-semibold">Our response: </span>{note.response}
              </p>
            </li>
          ))}
        </ul>
      </InsightSection>

      <InsightSection
        icon={FileText}
        title="Documents"
        summary={`${detail.documents.length} documents shared`}
      >
        {detail.documents.length === 0 ? (
          <AiEmptyState icon={FileText} title="No documents shared" description="Nothing has been shared with this account yet." size="inline" />
        ) : (
          <ul className="space-y-1.5">
            {detail.documents.map(document => (
              <li key={document.id} className="surface-2 bd flex items-center gap-3 rounded-xl border p-2.5">
                <span className="surface bd grid h-8 w-8 shrink-0 place-items-center rounded-lg border text-[9px] font-bold" aria-hidden="true">
                  {document.type}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="txt truncate text-[12.5px] font-medium" title={document.name}>{document.name}</p>
                  <p className="txt-faint text-[11px]">
                    {document.sizeKb} KB · shared {formatDate(document.sharedOn)}
                    {document.lastViewed ? ` · viewed ${formatDate(document.lastViewed)}` : ' · not viewed'}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="txt-faint mt-2.5 text-[11.5px]">
          Document metadata only — this screen has no file storage behind it.
        </p>
      </InsightSection>
    </div>
  );

  const tabs: TabDef[] = [
    { id: 'overview', label: 'Overview', content: overviewTab },
    { id: 'engagement', label: 'Engagement', content: engagementTab },
    { id: 'recommendations', label: 'AI Recommendations', content: recommendationsTab },
    { id: 'deal', label: 'Deal', content: dealTab },
  ];

  return (
    <SlideDrawer
      open={open}
      onClose={onClose}
      title={record.leadName}
      subtitle={`${record.company} · ${record.opportunity}`}
      width="max-w-3xl"
      footer={
        <>
          <button
            type="button"
            onClick={() => onRegenerate(record)}
            disabled={regenerating}
            className="ctl flex items-center gap-2 px-4 py-2.5 text-[13px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className={regenerating ? 'h-4 w-4 motion-safe:animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            {regenerating ? 'Regenerating…' : 'Regenerate'}
          </button>
          <button
            type="button"
            onClick={() => onMarkCompleted(record)}
            disabled={completed}
            className="flex items-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            {completed ? 'Completed' : 'Mark completed'}
          </button>
        </>
      }
    >
      {/* ── Context header ── */}
      <div className="surface-2 bd mb-4 rounded-2xl border p-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="txt-muted flex items-center gap-1.5 text-[12.5px] font-medium">
            <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
            {record.company}
          </span>
          <StatusBadge label={record.stage} variant="accent" />
          <StatusBadge label={record.priority} variant={PRIORITY_VARIANT[record.priority]} />
          <StatusBadge label={record.status} variant={STATUS_VARIANT[record.status]} />
          <StatusBadge label={`${record.dealRisk} risk`} variant={RISK_VARIANT[record.dealRisk]} />
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <HeaderStat label="Opportunity value" value={formatCurrency(record.expectedRevenue)} />
          <HeaderStat label="Win probability" value={`${record.winProbability}%`} />
          <HeaderStat label="AI confidence" value={`${record.confidence}%`} />
          <HeaderStat label="Assigned to" value={record.assignedTo} />
        </div>

        <div className="mt-3">
          <ScoreMeter
            value={record.confidence}
            label="AI confidence"
            tone={toneForScore(record.confidence)}
            size="sm"
            hideLabel
          />
        </div>
      </div>

      {/* ── Tabbed intelligence ── */}
      {loading || !detail ? <DetailSkeleton /> : <Tabs tabs={tabs} className="pb-2" />}
    </SlideDrawer>
  );
}
