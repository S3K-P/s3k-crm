'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  KeyRound,
  Loader2,
  Pencil,
  ShieldCheck,
  ShieldOff,
  UserPlus,
  Users,
  X,
} from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import { useAuth, usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import {
  MEMBERSHIP_STATUSES,
  addMember,
  createUser,
  listMembers,
  resetMemberPassword,
  setMemberStatus,
  updateMember,
  type MembershipStatus,
  type OrganizationMember,
} from '@/features/admin/users';
import { assignRole, listRoles, revokeRole, type Role } from '@/features/admin/roles';

/* ============================================================
   ADMIN — USERS

   Real members of the active organization, from
   `GET /api/v1/organizations/current/members`.

   Every action here changes what the person can actually do,
   because it changes the row the backend authorizes against on
   every request — not a label. Suspending a member cuts their
   access on their next call; revoking a role narrows what the
   API answers for them without them signing in again.

   Two guards the backend enforces and this screen explains
   rather than hides:

   - you cannot deactivate your own membership;
   - an organization must keep one active administrator, so the
     last Admin role cannot be revoked or suspended away.

   Both come back as real errors if the UI is bypassed.
   ============================================================ */

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...MEMBERSHIP_STATUSES.map((value) => ({ value, label: humanize(value) })),
];

type AddMode = 'create' | 'link';

interface NewUserForm {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
  phone: string;
  role_id: string;
}

const EMPTY_NEW_USER: NewUserForm = {
  email: '',
  first_name: '',
  last_name: '',
  password: '',
  phone: '',
  role_id: '',
};

interface EditForm {
  first_name: string;
  last_name: string;
  phone: string;
  timezone: string;
}

/** Mirrors the backend default (`Settings.password_min_length`). */
const MIN_PASSWORD_LENGTH = 12;

function describeName(member: OrganizationMember): string {
  return member.full_name?.trim() || member.email || 'this member';
}

function formatWhen(iso: string | null): string {
  if (!iso) return 'Never';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'Never';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function AdminUsersPage() {
  const confirm = useConfirm();
  const { currentUser } = useAuth();
  /* Used only to stop an administrator aiming a destructive action at their
     own membership; the backend refuses it regardless. */
  const signedInUserId = currentUser?.user.id ?? null;
  const { can } = usePermissions();
  const mayCreate = can('users', 'CREATE');
  const mayEdit = can('users', 'EDIT');
  const mayResetPassword = can('users', 'ADMIN');
  const mayAssignRoles = can('roles', 'ADMIN');

  const [members, setMembers] = useState<OrganizationMember[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const [attempt, setAttempt] = useState(0);

  /** Re-fetch the member list. Called after any mutation. */
  const reload = useCallback(() => {
    setRefreshing(true);
    setAttempt((n) => n + 1);
  }, []);

  // Inline rather than a callback the effect invokes, so no state is assigned
  // before the first await, and a superseded response cannot repaint the table.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const page = await listMembers();
        if (!cancelled) {
          setMembers(page.data);
          setTotal(page.total);
          setLoadError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setMembers(null);
          setLoadError(describeApiError(caught, 'Could not load the member list.'));
        }
      } finally {
        if (!cancelled) setRefreshing(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  /* ---- Roles, for the assignment picker ---- */
  const [roles, setRoles] = useState<Role[]>([]);
  useEffect(() => {
    if (!mayAssignRoles && !mayCreate) return;
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await listRoles();
        if (!cancelled) setRoles(loaded);
      } catch {
        // Members still list; the role picker stays empty.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayAssignRoles, mayCreate]);

  /* The endpoint offers neither search nor a status filter, so both are
     applied over the fetched window rather than pretended to be server-side. */
  const filtered = useMemo(() => {
    let rows = members ?? [];
    const term = search.trim().toLowerCase();
    if (term) {
      rows = rows.filter(
        (row) =>
          row.email.toLowerCase().includes(term) ||
          (row.full_name ?? '').toLowerCase().includes(term),
      );
    }
    if (statusFilter) rows = rows.filter((row) => row.status === statusFilter);
    return rows;
  }, [members, search, statusFilter]);

  /** Administrators still holding an active membership. Drives the UI half of
   *  the last-administrator guard; the backend enforces the real one. */
  const activeAdminCount = useMemo(
    () =>
      (members ?? []).filter(
        (row) => row.status === 'ACTIVE' && row.roles.includes('Admin'),
      ).length,
    [members],
  );

  const { pending, error: mutationError, clearError, run } = useMutation();
  const [working, setWorking] = useState<string | null>(null);

  /* ---- Activate / deactivate ---- */
  const handleStatus = async (member: OrganizationMember, next: MembershipStatus) => {
    const name = describeName(member);
    const deactivating = next !== 'ACTIVE';

    if (deactivating) {
      const ok = await confirm({
        title: `Deactivate ${name}?`,
        description:
          'They stay in the member list and keep their history, but the API stops answering for them from their very next request — no sign-out needed. Reactivating restores the same roles.',
        confirmLabel: 'Deactivate member',
        tone: 'danger',
      });
      if (!ok) return;
    } else {
      const ok = await confirm({
        title: `Reactivate ${name}?`,
        description: `Access is restored immediately, with the roles they already hold${
          member.roles.length > 0 ? `: ${member.roles.join(', ')}` : ' (none yet)'
        }.`,
        confirmLabel: 'Reactivate member',
        tone: 'warning',
      });
      if (!ok) return;
    }

    setWorking(member.user_id);
    try {
      await setMemberStatus(member.user_id, next);
      notifySuccess(deactivating ? 'Member deactivated' : 'Member reactivated', name);
      reload();
    } catch (caught) {
      // Covers both backend guards: self-deactivation and the last admin.
      notifyError(caught, 'The member status could not be changed.');
    } finally {
      setWorking(null);
    }
  };

  /* ---- Add: provision a new identity, or link an existing one ---- */
  const [addOpen, setAddOpen] = useState(false);
  const [addMode, setAddMode] = useState<AddMode>('create');
  const [newUser, setNewUser] = useState<NewUserForm>(EMPTY_NEW_USER);
  const [userId, setUserId] = useState('');
  const [roleId, setRoleId] = useState('');

  const openAdd = () => {
    clearError();
    setAddMode('create');
    setNewUser(EMPTY_NEW_USER);
    setUserId('');
    setRoleId('');
    setAddOpen(true);
  };

  const newUserValid =
    newUser.email.trim().length > 0 &&
    newUser.first_name.trim().length > 0 &&
    newUser.last_name.trim().length > 0 &&
    newUser.password.length >= MIN_PASSWORD_LENGTH;

  const handleAdd = async () => {
    if (addMode === 'link') {
      if (!userId.trim()) return;
      const added = await run(() =>
        addMember({ user_id: userId.trim(), role_id: roleId || null }),
      );
      if (added === undefined) return;
      setAddOpen(false);
      notifySuccess('Member added', describeName(added));
      reload();
      return;
    }

    if (!newUserValid) return;
    const created = await run(() =>
      createUser({
        email: newUser.email.trim().toLowerCase(),
        first_name: newUser.first_name.trim(),
        last_name: newUser.last_name.trim(),
        password: newUser.password,
        phone: newUser.phone.trim() || null,
        role_id: newUser.role_id || null,
      }),
    );
    if (created === undefined) return;
    setAddOpen(false);
    notifySuccess(
      'User created',
      `${describeName(created)} can sign in with the password you set.`,
    );
    reload();
  };

  /* ---- Edit details ---- */
  const [editTarget, setEditTarget] = useState<OrganizationMember | null>(null);
  const [editForm, setEditForm] = useState<EditForm>({
    first_name: '',
    last_name: '',
    phone: '',
    timezone: '',
  });

  const openEdit = (member: OrganizationMember) => {
    clearError();
    setEditForm({
      first_name: member.first_name ?? '',
      last_name: member.last_name ?? '',
      phone: member.phone ?? '',
      timezone: member.timezone ?? '',
    });
    setEditTarget(member);
  };

  const handleEdit = async () => {
    if (editTarget === null) return;
    if (!editForm.first_name.trim() || !editForm.last_name.trim()) return;
    const saved = await run(() =>
      updateMember(editTarget.user_id, {
        first_name: editForm.first_name.trim(),
        last_name: editForm.last_name.trim(),
        // An empty string clears the phone; `null` would mean "unchanged".
        phone: editForm.phone.trim(),
        timezone: editForm.timezone.trim() || null,
      }),
    );
    if (saved === undefined) return;
    setEditTarget(null);
    notifySuccess('Details updated', describeName(saved));
    reload();
  };

  /* ---- Roles ---- */
  const [roleTarget, setRoleTarget] = useState<OrganizationMember | null>(null);
  const [grantRoleId, setGrantRoleId] = useState('');

  const handleGrantRole = async () => {
    if (roleTarget === null || !grantRoleId) return;
    const role = roles.find((candidate) => candidate.id === grantRoleId);
    const name = describeName(roleTarget);

    const ok = await confirm({
      title: `Grant "${role?.name ?? 'this role'}" to ${name}?`,
      description:
        'This changes what the API allows them to do, immediately and without them signing in again. Roles add up: they keep everything their existing roles already grant.',
      confirmLabel: 'Grant role',
      tone: 'warning',
    });
    if (!ok) return;

    const done = await run(() => assignRole(roleTarget.id, grantRoleId));
    if (done === undefined) return;
    setRoleTarget(null);
    setGrantRoleId('');
    notifySuccess('Role granted', `${role?.name ?? 'Role'} → ${name}`);
    reload();
  };

  const handleRevokeRole = async (member: OrganizationMember, role: { id: string; name: string }) => {
    const name = describeName(member);
    const ok = await confirm({
      title: `Revoke "${role.name}" from ${name}?`,
      description:
        role.name === 'Admin'
          ? 'They lose administrative access at once. The organization must keep at least one active administrator, so this is refused if they are the last one.'
          : 'Everything that role granted stops working for them on their next request.',
      confirmLabel: 'Revoke role',
      tone: 'danger',
    });
    if (!ok) return;

    setWorking(member.user_id);
    try {
      await revokeRole(member.id, role.id);
      notifySuccess('Role revoked', `${role.name} × ${name}`);
      reload();
    } catch (caught) {
      notifyError(caught, 'The role could not be revoked.');
    } finally {
      setWorking(null);
    }
  };

  /* ---- Password reset ---- */
  const handleResetPassword = async (member: OrganizationMember) => {
    const name = describeName(member);
    const answer = await confirm({
      title: `Reset the password for ${name}?`,
      description: `Their current password stops working and every session they hold is revoked. Tell them the new password over a channel you trust — it is not emailed. Minimum ${MIN_PASSWORD_LENGTH} characters, with upper and lower case and a digit.`,
      confirmLabel: 'Reset password',
      tone: 'danger',
      prompt: {
        label: 'New password',
        required: true,
        multiline: false,
        placeholder: 'At least 12 characters',
      },
    });
    if (!answer) return;

    setWorking(member.user_id);
    try {
      await resetMemberPassword(member.user_id, answer.value);
      notifySuccess('Password reset', `${name} has been signed out everywhere.`);
      reload();
    } catch (caught) {
      // Typically the password policy — shown verbatim so the next attempt
      // can actually satisfy it.
      notifyError(caught, 'The password could not be reset.');
    } finally {
      setWorking(null);
    }
  };

  const columns = useMemo<ColumnDef<OrganizationMember>[]>(
    () => [
      {
        key: 'email',
        label: 'Member',
        minWidth: '220px',
        render: (row) => (
          <div className="flex flex-col">
            <span className="txt text-[13px] font-semibold">
              {row.full_name ?? row.email ?? 'Unnamed member'}
              {row.user_id === signedInUserId && (
                <span className="txt-faint ml-1.5 text-[11px] font-medium">(you)</span>
              )}
            </span>
            {row.full_name && row.email && (
              <span className="txt-faint mt-0.5 text-[11.5px]">{row.email}</span>
            )}
          </div>
        ),
      },
      {
        key: 'roles',
        label: 'Roles',
        minWidth: '180px',
        render: (row) =>
          row.role_details.length === 0 ? (
            <span className="txt-faint text-[12.5px]">No role — no access</span>
          ) : (
            <div className="flex flex-wrap items-center gap-1">
              {row.role_details.map((role) => (
                <span key={role.id} className="inline-flex items-center gap-0.5">
                  <StatusBadge label={role.name} variant="accent" />
                  {mayAssignRoles && (
                    <button
                      type="button"
                      aria-label={`Revoke ${role.name} from ${describeName(row)}`}
                      title={`Revoke ${role.name}`}
                      disabled={working === row.user_id}
                      onClick={() => void handleRevokeRole(row, role)}
                      className="txt-faint rounded p-0.5 transition hover:text-red-500 disabled:opacity-40"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </span>
              ))}
            </div>
          ),
      },
      {
        key: 'status',
        label: 'Status',
        render: (row) => (
          <StatusBadge label={humanize(row.status)} variant={statusVariant(row.status)} />
        ),
      },
      {
        key: 'last_login_at',
        label: 'Last sign-in',
        hideBelow: 'lg',
        render: (row) => (
          <span className="txt-muted text-[12.5px]">{formatWhen(row.last_login_at)}</span>
        ),
      },
      {
        key: 'actions',
        label: '',
        align: 'right',
        minWidth: '150px',
        render: (row) => {
          const busy = working === row.user_id;
          /* The screen mirrors the backend guards so the control is disabled
             rather than failing on click. The server still decides. */
          const isSelf = row.user_id === signedInUserId;
          const isLastAdmin =
            row.status === 'ACTIVE' && row.roles.includes('Admin') && activeAdminCount <= 1;

          return (
            <div className="flex items-center justify-end gap-1">
              {mayEdit && (
                <button
                  type="button"
                  aria-label={`Edit ${describeName(row)}`}
                  title="Edit details"
                  onClick={() => openEdit(row)}
                  className="ctl rounded-lg p-1.5 transition hover:opacity-70"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}
              {mayAssignRoles && (
                <button
                  type="button"
                  aria-label={`Assign a role to ${describeName(row)}`}
                  title="Grant a role"
                  onClick={() => {
                    clearError();
                    setGrantRoleId('');
                    setRoleTarget(row);
                  }}
                  className="ctl rounded-lg p-1.5 transition hover:opacity-70"
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                </button>
              )}
              {mayResetPassword && (
                <button
                  type="button"
                  aria-label={`Reset the password for ${describeName(row)}`}
                  title="Reset password"
                  disabled={busy}
                  onClick={() => void handleResetPassword(row)}
                  className="ctl rounded-lg p-1.5 transition hover:opacity-70 disabled:opacity-50"
                >
                  <KeyRound className="h-3.5 w-3.5" />
                </button>
              )}
              {mayEdit &&
                (row.status === 'ACTIVE' ? (
                  <button
                    type="button"
                    aria-label={`Deactivate ${describeName(row)}`}
                    title={
                      isSelf
                        ? 'You cannot deactivate your own membership'
                        : isLastAdmin
                          ? 'The last active administrator cannot be deactivated'
                          : 'Deactivate'
                    }
                    onClick={() => void handleStatus(row, 'SUSPENDED')}
                    disabled={busy || isSelf || isLastAdmin}
                    className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
                    ) : (
                      <ShieldOff className="h-3.5 w-3.5" />
                    )}
                  </button>
                ) : (
                  <button
                    type="button"
                    aria-label={`Reactivate ${describeName(row)}`}
                    title="Reactivate"
                    onClick={() => void handleStatus(row, 'ACTIVE')}
                    disabled={busy}
                    className="ctl rounded-lg p-1.5 transition hover:opacity-70 disabled:opacity-50"
                  >
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
                    ) : (
                      <ShieldCheck className="h-3.5 w-3.5" />
                    )}
                  </button>
                ))}
            </div>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mayEdit, mayAssignRoles, mayResetPassword, working, signedInUserId, activeAdminCount],
  );

  const roleOptions = roles.map((role) => ({
    value: role.id,
    label: role.is_system ? `${role.name} (system)` : role.name,
  }));

  return (
    <div className="mx-auto flex h-full max-w-7xl flex-col space-y-5 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-violet-600">
            <Users className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Users</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              People with access to this organization, and the roles that decide what they can
              do.
            </p>
          </div>
        </div>
        {mayCreate && (
          <button
            type="button"
            onClick={openAdd}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <UserPlus className="h-4 w-4" /> Add user
          </button>
        )}
      </div>

      <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center">
        <SearchInput
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search members…"
        />
        <FilterSelect
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          options={STATUS_OPTIONS}
        />
        {refreshing && (
          <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Refreshing" />
        )}
        <div className="ml-auto">
          <ResultCount shown={filtered.length} total={total} />
        </div>
      </div>

      <FormError message={mutationError} />

      {loadError !== null ? (
        <ListError message={loadError} onRetry={reload} />
      ) : (
        <DataTable
          columns={columns}
          data={filtered}
          rowKey={(row) => row.id}
          loading={members === null}
          skeletonRows={5}
          emptyState={
            <ListEmpty
              title="No members match"
              hint={
                search || statusFilter
                  ? 'No member matches those filters.'
                  : 'This organization has no members yet.'
              }
            />
          }
        />
      )}

      {/* ---- Add user ---- */}
      <SlideDrawer
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add user"
        subtitle="Create a new S3K account, or give an existing one access here."
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleAdd()}
              disabled={pending || (addMode === 'create' ? !newUserValid : !userId.trim())}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending
                ? 'Saving…'
                : addMode === 'create'
                  ? 'Create user'
                  : 'Add member'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <FormField label="How">
            <FormSelect
              value={addMode}
              onChange={(event) => {
                clearError();
                setAddMode(event.target.value as AddMode);
              }}
              options={[
                { value: 'create', label: 'Create a new user account' },
                { value: 'link', label: 'Add an existing S3K account by id' },
              ]}
            />
          </FormField>

          {addMode === 'create' ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <FormField label="First name" required>
                  <FormInput
                    value={newUser.first_name}
                    onChange={(event) =>
                      setNewUser({ ...newUser, first_name: event.target.value })
                    }
                  />
                </FormField>
                <FormField label="Last name" required>
                  <FormInput
                    value={newUser.last_name}
                    onChange={(event) =>
                      setNewUser({ ...newUser, last_name: event.target.value })
                    }
                  />
                </FormField>
              </div>
              <FormField label="Email" required hint="Also the sign-in name. Must be unique.">
                <FormInput
                  type="email"
                  value={newUser.email}
                  onChange={(event) => setNewUser({ ...newUser, email: event.target.value })}
                  autoComplete="off"
                />
              </FormField>
              <FormField
                label="Initial password"
                required
                hint={`At least ${MIN_PASSWORD_LENGTH} characters, with upper and lower case and a digit. Share it over a channel you trust — nothing is emailed.`}
                error={
                  newUser.password.length > 0 && newUser.password.length < MIN_PASSWORD_LENGTH
                    ? `Too short — ${MIN_PASSWORD_LENGTH} characters minimum.`
                    : undefined
                }
              >
                <FormInput
                  type="password"
                  value={newUser.password}
                  onChange={(event) => setNewUser({ ...newUser, password: event.target.value })}
                  autoComplete="new-password"
                />
              </FormField>
              <FormField label="Phone">
                <FormInput
                  value={newUser.phone}
                  onChange={(event) => setNewUser({ ...newUser, phone: event.target.value })}
                />
              </FormField>
              <FormField
                label="Role"
                hint="A member with no role can sign in but the API answers nothing for them."
              >
                <FormSelect
                  value={newUser.role_id}
                  onChange={(event) => setNewUser({ ...newUser, role_id: event.target.value })}
                  placeholder="No role"
                  options={roleOptions}
                />
              </FormField>
            </>
          ) : (
            <>
              <FormField
                label="User id"
                required
                hint="The UUID of an existing S3K account. There is no directory search endpoint yet."
              >
                <FormInput
                  value={userId}
                  onChange={(event) => setUserId(event.target.value)}
                  placeholder="00000000-0000-0000-0000-000000000000"
                />
              </FormField>
              {mayAssignRoles && (
                <FormField label="Role" hint="Optional. Can also be granted afterwards.">
                  <FormSelect
                    value={roleId}
                    onChange={(event) => setRoleId(event.target.value)}
                    placeholder="No role"
                    options={roleOptions}
                  />
                </FormField>
              )}
            </>
          )}

          <FormError message={mutationError} />
        </div>
      </SlideDrawer>

      {/* ---- Edit details ---- */}
      <SlideDrawer
        open={editTarget !== null}
        onClose={() => setEditTarget(null)}
        title="Edit details"
        subtitle={editTarget ? describeName(editTarget) : undefined}
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditTarget(null)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleEdit()}
              disabled={
                pending || !editForm.first_name.trim() || !editForm.last_name.trim()
              }
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <FormField label="First name" required>
              <FormInput
                value={editForm.first_name}
                onChange={(event) =>
                  setEditForm({ ...editForm, first_name: event.target.value })
                }
              />
            </FormField>
            <FormField label="Last name" required>
              <FormInput
                value={editForm.last_name}
                onChange={(event) =>
                  setEditForm({ ...editForm, last_name: event.target.value })
                }
              />
            </FormField>
          </div>
          <FormField label="Phone">
            <FormInput
              value={editForm.phone}
              onChange={(event) => setEditForm({ ...editForm, phone: event.target.value })}
            />
          </FormField>
          <FormField label="Timezone" hint="IANA name, e.g. Europe/London or Asia/Kolkata.">
            <FormInput
              value={editForm.timezone}
              onChange={(event) => setEditForm({ ...editForm, timezone: event.target.value })}
              placeholder="UTC"
            />
          </FormField>
          {editTarget !== null && (
            <p className="txt-faint text-[12px]">
              Email addresses cannot be changed here — an address is the identity itself, and
              the backend exposes no route to move one.
            </p>
          )}
          <FormError message={mutationError} />
        </div>
      </SlideDrawer>

      {/* ---- Grant a role ---- */}
      <SlideDrawer
        open={roleTarget !== null}
        onClose={() => setRoleTarget(null)}
        title="Grant role"
        subtitle={roleTarget ? describeName(roleTarget) : undefined}
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setRoleTarget(null)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleGrantRole()}
              disabled={pending || !grantRoleId}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending ? 'Granting…' : 'Grant role'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <FormField label="Role" required>
            <FormSelect
              value={grantRoleId}
              onChange={(event) => setGrantRoleId(event.target.value)}
              placeholder="Choose a role…"
              options={roleOptions.filter(
                (option) =>
                  !(roleTarget?.role_details ?? []).some((held) => held.id === option.value),
              )}
            />
          </FormField>
          {roleTarget !== null && roleTarget.roles.length > 0 && (
            <p className="txt-faint text-[12px]">
              Currently holds: {roleTarget.roles.join(', ')}. Revoke a role from the × beside
              its badge in the table.
            </p>
          )}
          <p className="txt-muted text-[12px]">
            What each role grants is shown on the{' '}
            <a href="/admin/roles" className="font-semibold" style={{ color: 'var(--accent)' }}>
              Roles &amp; permissions
            </a>{' '}
            matrix, which reads the same catalogue the API enforces.
          </p>
          <FormError message={mutationError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
