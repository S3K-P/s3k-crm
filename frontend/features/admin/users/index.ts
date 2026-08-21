/**
 * Organization members — the real backing for the admin Users screen.
 *
 * Mirrors the response models declared inline in
 * `backend/app/platform/organizations/router.py`.
 *
 * **Scope note.** These endpoints manage *membership of the active
 * organization*, not global user accounts. The backend exposes no
 * user-creation route (`AuthService.register_user` is reachable only through
 * `app.bootstrap`), so a person must already have an S3K identity before they
 * can be added here. Provisioning a brand-new user is a backend gap, recorded
 * as such rather than faked with a client-side stub.
 *
 * The endpoint paginates with `limit`/`offset` and offers no search or status
 * filter, so filtering happens in the page over a single fetched window. That
 * is honest for a member list — see `MEMBER_WINDOW`.
 */

import { api } from '@/lib/api-client';
import type { MembershipStatus } from '@/features/auth/types';

export type { MembershipStatus };

export const MEMBERSHIP_STATUSES: MembershipStatus[] = ['ACTIVE', 'INVITED', 'SUSPENDED'];

/** Largest page the backend allows (`Query(ge=1, le=200)`). */
export const MEMBER_WINDOW = 200;

/** A role the member holds. The id is what revocation needs. */
export interface MemberRole {
  id: string;
  name: string;
  is_system: boolean;
}

export interface OrganizationMember {
  /** Membership id — the handle role assignment uses, **not** the user id. */
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  status: MembershipStatus;
  is_default: boolean;
  /** Role names, for badges. */
  roles: string[];
  /** The same roles with ids, so a grant can be taken back again. */
  role_details: MemberRole[];
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  timezone: string | null;
  last_login_at: string | null;
  /** Platform identity status, distinct from membership status. */
  user_status: string;
}

export interface MemberListResponse {
  data: OrganizationMember[];
  total: number;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  status: 'ACTIVE' | 'SUSPENDED' | 'ARCHIVED';
}

export const listMembers = (params?: { limit?: number; offset?: number }) => {
  const query = new URLSearchParams({
    limit: String(params?.limit ?? MEMBER_WINDOW),
    offset: String(params?.offset ?? 0),
  });
  return api.get<MemberListResponse>(`/organizations/current/members?${query.toString()}`);
};

export const listMyOrganizations = () => api.get<OrganizationSummary[]>('/organizations');

export const getCurrentOrganization = () =>
  api.get<OrganizationSummary>('/organizations/current');

/** Adds an *existing* user to this organization, optionally with a role. */
export const addMember = (body: { user_id: string; role_id?: string | null }) =>
  api.post<OrganizationMember>('/organizations/current/members', body);

export interface CreateUserInput {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
  role_id?: string | null;
  phone?: string | null;
}

/**
 * Provision a brand-new identity and add it to this organization.
 *
 * Identity, profile, membership and the role grant happen in one backend
 * transaction, so a rejected role cannot leave a half-created user behind.
 */
export const createUser = (body: CreateUserInput) =>
  api.post<OrganizationMember>('/organizations/current/users', body);

export interface MemberProfileInput {
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  timezone?: string | null;
}

/** Edit a member's display details. Omitted fields are left unchanged. */
export const updateMember = (userId: string, body: MemberProfileInput) =>
  api.patch<OrganizationMember>(`/organizations/current/members/${userId}`, body);

/** Keyed by **user** id, which is what the route takes — not membership id. */
export const setMemberStatus = (userId: string, status: MembershipStatus) =>
  api.post<OrganizationMember>(`/organizations/current/members/${userId}/status`, {
    status,
  });

/**
 * Replace a member's password administratively.
 *
 * Requires `users.ADMIN`. The backend revokes every session the member holds,
 * so they are signed out everywhere. Returns no body — echoing a live
 * credential back would only put it in another log.
 */
export const resetMemberPassword = (userId: string, newPassword: string) =>
  api.post<void>(`/organizations/current/members/${userId}/reset-password`, {
    new_password: newPassword,
  });
