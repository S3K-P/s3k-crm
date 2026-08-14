/**
 * Auth contracts, mirroring the backend's Pydantic response models.
 *
 * Hand-written for now. Doc 11 calls for an `orval`-generated client from the
 * OpenAPI schema; these types are the boundary that generation will replace,
 * and nothing above them needs to change when it does.
 */

export interface UserProfile {
  first_name: string;
  last_name: string;
  avatar_url: string | null;
  timezone: string;
  locale: string;
  phone: string | null;
}

export type UserStatus = 'ACTIVE' | 'DISABLED' | 'PENDING';

export interface User {
  id: string;
  email: string;
  status: UserStatus;
  email_verified_at: string | null;
  last_login_at: string | null;
  profile: UserProfile | null;
}

export type MembershipStatus = 'ACTIVE' | 'INVITED' | 'SUSPENDED';

export interface Membership {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  status: MembershipStatus;
  is_default: boolean;
  roles: string[];
}

/** `GET /auth/me` — identity, memberships and effective permissions. */
export interface CurrentUser {
  user: User;
  memberships: Membership[];
  active_organization_id: string | null;
  /** `module.ACTION` codes for the **active** organization only. */
  permissions: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  organization_id: string | null;
}

export interface LoginCredentials {
  email: string;
  password: string;
  organization_id?: string;
}

/** The six actions every module supports. */
export type PermissionAction = 'VIEW' | 'CREATE' | 'EDIT' | 'DELETE' | 'EXPORT' | 'ADMIN';

/** Build a permission code, e.g. `permission('leads', 'CREATE')`. */
export function permission(module: string, action: PermissionAction): string {
  return `${module}.${action}`;
}
