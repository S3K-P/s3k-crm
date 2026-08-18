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
};

export function statusVariant(value: string | null | undefined): BadgeVariant {
  if (!value) return 'neutral';
  return VARIANTS[value] ?? 'neutral';
}
