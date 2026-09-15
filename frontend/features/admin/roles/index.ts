/**
 * Roles and permissions — the real backing for the admin Roles matrix.
 *
 * Mirrors the response models in
 * `backend/app/platform/authorization/router.py`.
 *
 * The catalogue (`modules` × `actions`) and the roles list both come from the
 * backend, so the matrix renders exactly the vocabulary the API enforces. A
 * module added to `catalog.py` appears here without a frontend change — which
 * is the point: a hardcoded matrix drifts from what is actually enforced, and
 * a permission matrix that lies is worse than no matrix.
 *
 * **System templates (Admin/Manager/User) stay read-only** — seeded by
 * migration, shared by every tenant. A tenant's **own** roles (Checkpoint 8)
 * can be created, renamed, re-permissioned and deleted through
 * `createRole`/`updateRole`/`deleteRole`; the backend refuses all three for a
 * system template (409 `conflict`) and refuses a delete while any member
 * still holds the role. Role *assignment* to a member is separate and
 * unchanged (`assignRole` / `revokeRole`).
 */

import { api } from '@/lib/api-client';
import type { PermissionAction } from '@/features/auth/types';

export type { PermissionAction };

export interface Role {
  id: string;
  /** `null` marks a system template shared by every organization. */
  organization_id: string | null;
  name: string;
  description: string | null;
  is_system: boolean;
}

export interface RoleDetail extends Role {
  /** `module.ACTION` codes this role grants. */
  permissions: string[];
}

export interface PermissionCatalog {
  modules: string[];
  actions: PermissionAction[];
  codes: string[];
}

export const listRoles = () => api.get<Role[]>('/roles');

export const getRole = (id: string) => api.get<RoleDetail>(`/roles/${id}`);

export const getPermissionCatalog = () =>
  api.get<PermissionCatalog>('/roles/permissions');

export interface RoleFormInput {
  name: string;
  description: string | null;
  permissions: string[];
}

export const createRole = (input: RoleFormInput) =>
  api.post<RoleDetail>('/roles', input);

/** Every field optional: only what's sent is changed — see the backend's `RoleUpdateRequest`. */
export const updateRole = (id: string, changes: Partial<RoleFormInput>) =>
  api.patch<RoleDetail>(`/roles/${id}`, changes);

export const deleteRole = (id: string) => api.delete<void>(`/roles/${id}`);

export const assignRole = (membershipId: string, roleId: string) =>
  api.post<void>('/roles/assignments', {
    membership_id: membershipId,
    role_id: roleId,
  });

export const revokeRole = (membershipId: string, roleId: string) =>
  api.post<void>('/roles/assignments/revoke', {
    membership_id: membershipId,
    role_id: roleId,
  });

/** Load every role together with its granted permissions, for the matrix. */
export async function loadRoleMatrix(): Promise<{
  catalog: PermissionCatalog;
  roles: RoleDetail[];
}> {
  const [catalog, roles] = await Promise.all([getPermissionCatalog(), listRoles()]);
  const detailed = await Promise.all(roles.map((role) => getRole(role.id)));
  return { catalog, roles: detailed };
}

/** Human label for a permission module, e.g. `lead_sources` → "Lead Sources". */
export function moduleLabel(module: string): string {
  return module
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
