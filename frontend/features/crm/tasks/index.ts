/**
 * Tasks — types and API access.
 *
 * Mirrors `backend/app/products/crm/tasks/schemas.py`. `completed_at` is
 * derived by the backend from the status, so it is read-only here.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

export type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';
export type Priority = 'HIGH' | 'MEDIUM' | 'LOW';
export type CrmEntityType = 'ACCOUNT' | 'CONTACT' | 'LEAD' | 'OPPORTUNITY' | 'CAMPAIGN';

export const TASK_STATUSES: TaskStatus[] = [
  'PENDING',
  'IN_PROGRESS',
  'COMPLETED',
  'CANCELLED',
];

export const TASK_PRIORITIES: Priority[] = ['HIGH', 'MEDIUM', 'LOW'];

/** Statuses that take a task off someone's plate. Mirrors CLOSED_STATUSES. */
export const CLOSED_TASK_STATUSES: TaskStatus[] = ['COMPLETED', 'CANCELLED'];

export interface Task extends RecordMeta {
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: Priority;
  due_date: string | null;
  completed_at: string | null;
  owner_id: string | null;
  assigned_to_id: string | null;
  related_entity_type: CrmEntityType | null;
  related_entity_id: string | null;
}

export interface TaskInput {
  title: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: Priority;
  due_date?: string | null;
  assigned_to_id?: string | null;
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
}

export interface TaskListParams extends ListParams {
  status?: TaskStatus | null;
  priority?: Priority | null;
  assigned_to_id?: string | null;
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
  open_only?: boolean;
}

export interface TaskStatusCounts {
  counts: Record<string, number>;
}

export const listTasks = (params?: TaskListParams) =>
  api.get<Page<Task>>(`/crm/tasks${toQuery(params)}`);

export const getTask = (id: string) => api.get<Task>(`/crm/tasks/${id}`);

export const taskStatusCounts = () => api.get<TaskStatusCounts>('/crm/tasks/status-counts');

export const createTask = (body: TaskInput) => api.post<Task>('/crm/tasks', body);

export const updateTask = (id: string, body: Partial<TaskInput>) =>
  api.patch<Task>(`/crm/tasks/${id}`, body);

export const changeTaskStatus = (id: string, status: TaskStatus) =>
  api.post<Task>(`/crm/tasks/${id}/status`, { status });

export const archiveTask = (id: string) => api.delete<void>(`/crm/tasks/${id}`);
