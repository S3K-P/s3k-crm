/**
 * Meetings — a view over activities, not a table of its own.
 *
 * The backend models a meeting as an `Activity` of type `MEETING` carrying a
 * one-to-one `meeting` extension (`crm.meetings`). There is no `/crm/meetings`
 * endpoint and there should not be: a meeting *is* an activity, and giving it
 * a second route would mean two places that can disagree about the timeline.
 *
 * This module is therefore a thin, deliberately narrow wrapper over the
 * activities API that pins `type=MEETING` so no caller can forget to.
 */

import {
  archiveActivity,
  createActivity,
  getActivity,
  listActivities,
  updateActivity,
  type Activity,
  type ActivityListParams,
  type ActivityStatus,
  type MeetingDetail,
  type MeetingType,
} from '@/features/crm/activities';
import type { CrmEntityType } from '@/features/crm/tasks';
import type { Page } from '@/features/shared/types/api';

export type { MeetingDetail, MeetingType };
export { MEETING_TYPES } from '@/features/crm/activities';

/**
 * An activity known to be a meeting.
 *
 * The backend guarantees the extension row exists whenever `type` is MEETING
 * (`ActivityCreate._meeting_detail_matches_type`), but the wire type cannot
 * express that, so `meeting` stays nullable and callers use `meetingDetail()`.
 */
export type Meeting = Activity;

/** Scheduling detail, or `null` if a record arrived without its extension. */
export const meetingDetail = (meeting: Meeting): MeetingDetail | null => meeting.meeting;

/** Meetings are "scheduled" until completed or cancelled. */
export type MeetingStatus = ActivityStatus;

export const MEETING_STATUSES: MeetingStatus[] = ['PLANNED', 'COMPLETED', 'CANCELLED'];

export interface MeetingListParams extends Omit<ActivityListParams, 'type'> {
  status?: ActivityStatus | null;
}

export interface MeetingInput {
  subject: string;
  description?: string | null;
  status?: ActivityStatus;
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
  meeting: Partial<MeetingDetail> & { start_time: string };
}

export const listMeetings = (params?: MeetingListParams): Promise<Page<Meeting>> =>
  listActivities({ ...params, type: 'MEETING' });

export const getMeeting = (id: string): Promise<Meeting> => getActivity(id);

export const createMeeting = (body: MeetingInput): Promise<Meeting> =>
  createActivity({ ...body, type: 'MEETING' });

/** `type` is immutable server-side, so it is never sent on update. */
export const updateMeeting = (
  id: string,
  body: Partial<Omit<MeetingInput, 'meeting'>> & { meeting?: MeetingInput['meeting'] },
): Promise<Meeting> => updateActivity(id, body);

export const archiveMeeting = (id: string): Promise<void> => archiveActivity(id);
