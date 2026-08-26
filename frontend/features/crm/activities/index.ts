/**
 * Activities and meetings — types and API access.
 *
 * Mirrors `backend/app/products/crm/activities/schemas.py`. A MEETING activity
 * always carries its scheduling detail; anything else never does.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';
import type { CrmEntityType } from '@/features/crm/tasks';

export type ActivityType = 'CALL' | 'EMAIL' | 'MEETING' | 'NOTE' | 'TASK';
export type ActivityStatus = 'PLANNED' | 'COMPLETED' | 'CANCELLED';
export type MeetingType = 'IN_PERSON' | 'VIDEO' | 'PHONE';

export const ACTIVITY_TYPES: ActivityType[] = ['CALL', 'EMAIL', 'MEETING', 'NOTE', 'TASK'];
export const ACTIVITY_STATUSES: ActivityStatus[] = ['PLANNED', 'COMPLETED', 'CANCELLED'];
export const MEETING_TYPES: MeetingType[] = ['IN_PERSON', 'VIDEO', 'PHONE'];

export interface MeetingDetail {
  meeting_type: MeetingType;
  start_time: string;
  end_time: string | null;
  location: string | null;
  meeting_link: string | null;
  agenda: string | null;
  reminder_minutes: number | null;
  internal_participant_ids: string[];
}

export interface Activity extends RecordMeta {
  type: ActivityType;
  subject: string;
  description: string | null;
  status: ActivityStatus;
  due_date: string | null;
  completed_at: string | null;
  outcome: string | null;
  owner_id: string | null;
  related_entity_type: CrmEntityType | null;
  related_entity_id: string | null;
  meeting: MeetingDetail | null;
}

export interface ActivityInput {
  type: ActivityType;
  subject: string;
  description?: string | null;
  status?: ActivityStatus;
  due_date?: string | null;
  outcome?: string | null;
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
  meeting?: Partial<MeetingDetail> & { start_time: string };
}

export interface ActivityListParams extends ListParams {
  type?: ActivityType | null;
  status?: ActivityStatus | null;
  owner_id?: string | null;
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
}

export const listActivities = (params?: ActivityListParams) =>
  api.get<Page<Activity>>(`/crm/activities${toQuery(params)}`);

export const getActivity = (id: string) => api.get<Activity>(`/crm/activities/${id}`);

/** Everything recorded against one record, most recent first. */
export const entityTimeline = (
  relatedEntityType: CrmEntityType,
  relatedEntityId: string,
  limit = 50,
) =>
  api.get<Activity[]>(
    `/crm/activities/timeline${toQuery({
      related_entity_type: relatedEntityType,
      related_entity_id: relatedEntityId,
      limit,
    })}`,
  );

export const createActivity = (body: ActivityInput) =>
  api.post<Activity>('/crm/activities', body);

export const updateActivity = (id: string, body: Partial<ActivityInput>) =>
  api.patch<Activity>(`/crm/activities/${id}`, body);

export const archiveActivity = (id: string) => api.delete<void>(`/crm/activities/${id}`);
