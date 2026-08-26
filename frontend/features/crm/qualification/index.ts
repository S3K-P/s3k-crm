/**
 * Qualification — a working view over leads, not a table of its own.
 *
 * **What is real:** the queue itself. A lead is "awaiting qualification" while
 * its status is NEW or CONTACTED, "qualified" at QUALIFIED, and out of the
 * queue once it is CONVERTED or LOST. All of that is real lead data, and the
 * actions the queue offers (advance the status, convert) are the same
 * rule-enforced endpoints the Leads screen uses.
 *
 * **What is not built:** the BANT / MEDDICC / CHAMP scorecard. It needs a
 * `QualificationRecord` table (MIP P2-W14-BE-04/05) which does not exist, so
 * there is nowhere to persist budget, authority, need or timeline. Rather than
 * render invented values, the screens say the scorecard is unavailable and
 * name what is missing.
 */

import {
  changeLeadStatus,
  listLeads,
  type Lead,
  type LeadListParams,
  type LeadStatus,
} from '@/features/crm/leads';
import type { Page } from '@/features/shared/types/api';

/** Where a lead sits relative to qualification. Derived, never stored. */
export type QualificationStage = 'AWAITING' | 'QUALIFIED' | 'CLOSED';

/** Statuses that put a lead in the qualification queue. */
export const AWAITING_STATUSES: LeadStatus[] = ['NEW', 'CONTACTED'];

/** Statuses that mean qualification finished and the deal moved on. */
export const CLOSED_STATUSES: LeadStatus[] = ['CONVERTED', 'LOST'];

export function qualificationStage(lead: Lead): QualificationStage {
  if (CLOSED_STATUSES.includes(lead.status)) return 'CLOSED';
  if (lead.status === 'QUALIFIED') return 'QUALIFIED';
  if (AWAITING_STATUSES.includes(lead.status)) return 'AWAITING';
  // PROPOSAL_SENT / NEGOTIATION are past qualification but still open.
  return 'QUALIFIED';
}

export const STAGE_LABELS: Record<QualificationStage, string> = {
  AWAITING: 'Awaiting review',
  QUALIFIED: 'Qualified',
  CLOSED: 'Closed',
};

export interface QualificationQueueParams extends Omit<LeadListParams, 'status'> {
  /** Restrict to one lead status; omit for the whole open queue. */
  status?: LeadStatus | null;
}

/**
 * One page of the qualification queue.
 *
 * With no `status` the backend returns every lead and the caller filters to
 * the open ones. The lead list endpoint takes a single status, not a set, so
 * narrowing to "NEW or CONTACTED" server-side is not expressible today.
 */
export const listQualificationQueue = (
  params?: QualificationQueueParams,
): Promise<Page<Lead>> => listLeads(params);

/** Mark a lead qualified. The backend rejects an illegal transition with 422. */
export const markQualified = (leadId: string) => changeLeadStatus(leadId, 'QUALIFIED');

/** Disqualify a lead, recording why. */
export const disqualify = (leadId: string, reason: string) =>
  changeLeadStatus(leadId, 'LOST', reason);

/**
 * Why the scorecard is missing. Rendered verbatim by both qualification
 * screens so the two never drift apart in what they claim.
 */
export const SCORECARD_UNAVAILABLE =
  'Structured qualification scoring (BANT / MEDDICC / CHAMP) needs the QualificationRecord ' +
  'table, which has not been built yet. Until it exists this screen shows the real lead ' +
  'pipeline only — no scorecard values are stored or displayed.';

export type { Lead, LeadStatus };
