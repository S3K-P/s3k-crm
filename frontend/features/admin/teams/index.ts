/**
 * Teams and departments — the real backing for the admin Teams screen.
 *
 * Mirrors `backend/app/platform/teams/schemas.py`.
 *
 * **Why this screen matters more than it looks.** Team membership is not
 * cosmetic grouping: it is an input to record-level visibility. A user holding
 * `<module>.VIEW_TEAM` can read records owned by anyone on a team they share,
 * so adding somebody to a team widens what they can see. That is why the page
 * confirms membership changes and why the backend audits every one of them.
 *
 * `VIEW_TEAM` itself is granted on the Roles screen, not here — this screen
 * decides who is on which team, the role decides whether that means anything.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page } from '@/features/shared/types/api';

export interface Department {
  id: string;
  organization_id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface Team {
  id: string;
  organization_id: string;
  name: string;
  department_id: string | null;
  created_at: string;
  updated_at: string;
  member_count: number;
}

export interface TeamMember {
  id: string;
  user_id: string;
  joined_at: string;
}

/** Largest page the backend allows (`Query(ge=1, le=200)`). */
export const TEAM_WINDOW = 200;

export interface TeamListParams extends ListParams {
  department_id?: string;
}

export const listTeams = (params: TeamListParams = {}) =>
  api.get<Page<Team>>(`/teams${toQuery(params)}`);

export const getTeam = (id: string) => api.get<Team>(`/teams/${id}`);

export const createTeam = (body: { name: string; department_id?: string | null }) =>
  api.post<Team>('/teams', body);

export const updateTeam = (
  id: string,
  body: { name?: string; department_id?: string | null },
) => api.patch<Team>(`/teams/${id}`, body);

export const deleteTeam = (id: string) => api.delete<void>(`/teams/${id}`);

export const listTeamMembers = (id: string, params: ListParams = {}) =>
  api.get<Page<TeamMember>>(`/teams/${id}/members${toQuery(params)}`);

export const addTeamMember = (id: string, userId: string) =>
  api.post<TeamMember>(`/teams/${id}/members`, { user_id: userId });

export const removeTeamMember = (id: string, userId: string) =>
  api.delete<void>(`/teams/${id}/members/${userId}`);

export const listDepartments = (params: ListParams = {}) =>
  api.get<Page<Department>>(`/departments${toQuery(params)}`);

export const createDepartment = (body: { name: string }) =>
  api.post<Department>('/departments', body);

export const deleteDepartment = (id: string) => api.delete<void>(`/departments/${id}`);
