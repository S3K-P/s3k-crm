import type { BadgeVariant } from '@/components/crm/shared/StatusBadge';

/* ============================================================
   STATUS PRESENTATION

   The API speaks in SCREAMING_SNAKE enum values because that is
   what the database stores. Screens speak in sentence case with
   a colour. Both mappings live here so a status renders
   identically on every page, and so adding a value to a backend
   enum has exactly one place to update.
   ============================================================ */

/** "PROPOSAL_SENT" -> "Proposal sent" */
export function humanize(value: string): string {
  const lower = value.replace(/_/g, ' ').toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

const VARIANTS: Record<string, BadgeVariant> = {
  // Shared
  ACTIVE: 'success',
  INACTIVE: 'neutral',
  CANCELLED: 'neutral',
  COMPLETED: 'success',

  // Accounts
  ONBOARDING: 'accent',
  AT_RISK: 'warning',
  CHURNED: 'danger',

  // Leads
  NEW: 'accent',
  CONTACTED: 'accent',
  QUALIFIED: 'success',
  PROPOSAL_SENT: 'warning',
  NEGOTIATION: 'warning',
  CONVERTED: 'success',
  UNQUALIFIED: 'danger',
  LOST: 'danger',

  // Tasks
  PENDING: 'neutral',
  IN_PROGRESS: 'accent',

  // Priority
  HIGH: 'danger',
  MEDIUM: 'warning',
  LOW: 'neutral',

  // Activities
  PLANNED: 'accent',

  // Campaigns
  PLANNING: 'neutral',
  PAUSED: 'warning',

  // Memberships
  INVITED: 'warning',
  SUSPENDED: 'danger',
  DISABLED: 'neutral',

  // Email.
  //
  // `QUEUED` is a warning rather than a neutral, and that is the point of
  // having it: a message still queued minutes after it was sent means the
  // worker is not draining the outbox, which is worth noticing rather than
  // blending into the list. `DRAFT` really is neutral — nothing is wrong with
  // an unsent message.
  DRAFT: 'neutral',
  QUEUED: 'warning',
  SENT: 'success',
  FAILED: 'danger',
};

export function statusVariant(value: string | null | undefined): BadgeVariant {
  if (!value) return 'neutral';
  return VARIANTS[value] ?? 'neutral';
}
