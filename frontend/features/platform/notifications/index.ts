/**
 * Notifications — types and API access.
 *
 * Mirrors `backend/app/platform/notifications/schemas.py`. Unlike every CRM
 * module, there is no `require_permission` gate behind these calls — a
 * notification is scoped to whoever is signed in, not to a role's reach; see
 * that module's `policies.py` for why.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page } from '@/features/shared/types/api';

export type NotificationKind = 'MEETING_REMINDER' | 'TASK_DUE' | 'RECORD_ASSIGNED';

export interface Notification {
  id: string;
  organization_id: string;
  kind: NotificationKind | string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListParams extends ListParams {
  unread_only?: boolean;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export const listNotifications = (params?: NotificationListParams) =>
  api.get<Page<Notification>>(`/notifications${toQuery(params)}`);

export const unreadNotificationCount = () =>
  api.get<UnreadCountResponse>('/notifications/unread-count');

export const markNotificationRead = (id: string) =>
  api.post<Notification>(`/notifications/${id}/read`);

export const markAllNotificationsRead = () =>
  api.post<UnreadCountResponse>('/notifications/read-all');
