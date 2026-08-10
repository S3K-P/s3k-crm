import type { BadgeVariant } from '@/components/crm/shared/StatusBadge';
import type { MeterTone } from '@/components/crm/ai/shared/ScoreMeter';
import type {
  DealRisk,
  NbaDetail,
  NbaPriority,
  NbaStatus,
  ProposalStatus,
  RiskSeverity,
  SowStatus,
} from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA PRESENTATION HELPERS
   Badge and tone mappings plus the plain-text serialisers used
   by the drawer's Copy actions.
   ============================================================ */

export const PRIORITY_VARIANT: Record<NbaPriority, BadgeVariant> = {
  Critical: 'danger',
  High: 'warning',
  Medium: 'accent',
  Low: 'neutral',
};

export const STATUS_VARIANT: Record<NbaStatus, BadgeVariant> = {
  New: 'accent',
  Pending: 'warning',
  'In Progress': 'accent',
  Scheduled: 'accent',
  Completed: 'success',
  Dismissed: 'neutral',
};

export const SEVERITY_VARIANT: Record<RiskSeverity, BadgeVariant> = {
  Critical: 'danger',
  High: 'danger',
  Medium: 'warning',
  Low: 'neutral',
};

export const RISK_VARIANT: Record<DealRisk, BadgeVariant> = {
  Low: 'success',
  Medium: 'warning',
  High: 'danger',
  Critical: 'danger',
};

export const PROPOSAL_VARIANT: Record<ProposalStatus, BadgeVariant> = {
  Draft: 'neutral',
  Sent: 'accent',
  Viewed: 'accent',
  'Under Review': 'warning',
  'Revision Requested': 'warning',
  Approved: 'success',
};

export const SOW_VARIANT: Record<SowStatus, BadgeVariant> = {
  'Not Started': 'neutral',
  Drafting: 'accent',
  Shared: 'accent',
  'Legal Review': 'warning',
  Approved: 'success',
};

export function confidenceTone(value: number): MeterTone {
  if (value >= 85) return 'positive';
  if (value >= 70) return 'accent';
  if (value >= 50) return 'caution';
  return 'negative';
}

export function confidenceLabel(value: number): string {
  if (value >= 85) return 'High confidence';
  if (value >= 70) return 'Good confidence';
  if (value >= 50) return 'Moderate confidence';
  return 'Low confidence';
}

/* ---- Copy serialisers ---- */

export function callScriptToText(sections: NbaDetail['callScript']): string {
  return sections
    .map(section => `${section.label.toUpperCase()}\n${section.lines.map(line => `  ${line}`).join('\n')}`)
    .join('\n\n');
}

export function agendaToText(items: NbaDetail['meetingAgenda']): string {
  const total = items.reduce((sum, item) => sum + item.minutes, 0);
  return `Suggested meeting agenda (${total} minutes)\n\n${items
    .map(
      (item, index) =>
        `${index + 1}. ${item.topic} — ${item.minutes} min\n   Objective: ${item.objective}\n   Participants: ${item.participants}`,
    )
    .join('\n')}`;
}

export function emailToText(email: NbaDetail['suggestedEmail']): string {
  return `Subject: ${email.subject}\n\n${email.body}`;
}
