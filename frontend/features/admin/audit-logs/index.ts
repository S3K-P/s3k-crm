/**
 * Audit logs — types and API access.
 *
 * Mirrors `backend/app/platform/audit/schemas.py` and the query parameters of
 * `GET /api/v1/audit-logs`.
 *
 * **Read-only, and that is not an omission.** The backend exposes no create,
 * update or delete route for the trail, and `platform.audit_logs` carries a
 * database trigger that rejects UPDATE and DELETE for every role. There is
 * nothing here to write with because there is nothing there to write to.
 *
 * Every filter below is applied server-side, against the caller's own
 * organization. Nothing is narrowed in the browser: a client-side filter over
 * a page of results would be both wrong (the count would not match) and
 * pointless as a control.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page } from '@/features/shared/types/api';

/** Outcome of the audited attempt. */
export type AuditStatus = 'SUCCESS' | 'FAILURE' | 'DENIED';

export interface AuditLogEntry {
  id: string;
  organization_id: string;
  created_at: string;

  actor_id: string | null;
  /** Joined from the directory at read time; null for system actions. */
  actor_email: string | null;
  actor_name: string | null;

  action: string;
  module: string;
  status: AuditStatus;

  entity_type: string | null;
  entity_id: string | null;
  /** The record's name as it was when the action happened. */
  entity_label: string | null;

  request_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  /** Redacted server-side before storage — never contains a credential. */
  details: Record<string, unknown> | null;
}

export interface AuditLogListParams extends ListParams {
  occurred_from?: string | null;
  occurred_to?: string | null;
  actor_id?: string | null;
  action?: string | null;
  module?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  status?: AuditStatus | null;
}

/** Filter values that actually occur in this organization's trail. */
export interface AuditFilterOptions {
  actions: string[];
  entity_types: string[];
  statuses: AuditStatus[];
  /** Oldest retained record, so "no results" can be told from "not that far back". */
  recording_since: string | null;
}

export const listAuditLogs = (params?: AuditLogListParams) =>
  api.get<Page<AuditLogEntry>>(`/audit-logs${toQuery(params)}`);

export const getAuditLog = (id: string) => api.get<AuditLogEntry>(`/audit-logs/${id}`);

export const getAuditFilterOptions = () =>
  api.get<AuditFilterOptions>('/audit-logs/filters');

/* ------------------------------------------------------------------
   Presentation helpers
   ------------------------------------------------------------------ */

/** `LEAD_STATUS_CHANGED` → `Lead status changed`. */
export function actionLabel(action: string): string {
  const lower = action.replace(/_/g, ' ').toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/**
 * Whether an action changes who can reach what.
 *
 * Used to mark the rows an administrator reviewing access should not have to
 * hunt for. Kept as a list rather than inferred from the module, because
 * `users.UPDATED` (a phone number) and `users.MEMBER_STATUS_CHANGED` (access
 * revoked) share a module and are not remotely the same event.
 */
const SECURITY_ACTIONS = new Set([
  'LOGIN_FAILED',
  'LOGIN_BLOCKED',
  'ACCOUNT_LOCKED',
  'TOKEN_REUSE_DETECTED',
  'PASSWORD_CHANGED',
  'PASSWORD_RESET_BY_ADMIN',
  'ROLE_ASSIGNED',
  'ROLE_REVOKED',
  'MEMBER_ADDED',
  'MEMBER_STATUS_CHANGED',
  'USER_PROVISIONED',
  'OWNER_REASSIGNED',
]);

export function isSecurityAction(action: string): boolean {
  return SECURITY_ACTIONS.has(action);
}

/** Badge colour for an outcome. */
export function statusVariantFor(status: AuditStatus): 'success' | 'danger' | 'warning' {
  if (status === 'SUCCESS') return 'success';
  if (status === 'DENIED') return 'warning';
  return 'danger';
}

/**
 * A one-line summary of what a record's `details` payload says.
 *
 * Deliberately lossy — the full payload is one click away in the detail
 * drawer. This is the column an administrator scans, so it answers "what
 * changed" in the fewest words the shape allows and gives up rather than
 * rendering something misleading.
 */
export function summariseDetails(entry: AuditLogEntry): string {
  const details = entry.details;
  if (details === null) return '—';

  const changes = details.changes;
  if (changes !== null && typeof changes === 'object') {
    const fields = Object.keys(changes as Record<string, unknown>);
    if (fields.length === 0) return '—';
    const shown = fields.slice(0, 3).join(', ');
    return fields.length > 3 ? `${shown} +${fields.length - 3} more` : shown;
  }

  if (typeof details.from === 'string' && typeof details.to === 'string') {
    return `${details.from} → ${details.to}`;
  }
  if (typeof details.reason === 'string') return details.reason;
  if (typeof details.to_stage === 'string') return `→ ${details.to_stage}`;

  const keys = Object.keys(details);
  return keys.length > 0 ? keys.slice(0, 3).join(', ') : '—';
}

/** ISO timestamp → the two-line form the table shows. */
export function formatTimestamp(iso: string): { date: string; time: string } {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return { date: iso, time: '' };
  return {
    date: at.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
    }),
    time: at.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }),
  };
}

/**
 * Local `datetime-local` input value → an instant the API accepts.
 *
 * The input yields wall-clock time with no zone; `new Date` reads it in the
 * viewer's zone, which is what they meant, and `toISOString` converts it to
 * the UTC the backend compares against. Skipping this step would silently
 * shift every date filter by the viewer's offset.
 */
export function toInstant(localValue: string): string | null {
  if (!localValue) return null;
  const at = new Date(localValue);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}
