'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, Pencil, Plus, Shield, Trash2, X } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize } from '@/components/crm/shared/statusVariants';
import { ListError } from '@/components/crm/shared/ListStates';
import { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import FormField, { FormInput, FormTextarea } from '@/components/crm/forms/FormField';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import {
  createRole,
  deleteRole,
  loadRoleMatrix,
  moduleLabel,
  updateRole,
  type PermissionCatalog,
  type RoleDetail,
} from '@/features/admin/roles';

/* ============================================================
   ADMIN — ROLES

   The permission matrix, rendered from what the backend actually
   enforces: `GET /roles/permissions` supplies the vocabulary and
   `GET /roles/{id}` supplies each role's grants.

   The previous version hardcoded eleven module names and five
   role names that matched neither the seeded roles nor the
   permission catalogue — so an administrator reading it would
   have drawn conclusions about access that were simply untrue.
   Rendering from the API means a module added to `catalog.py`
   shows up here without a frontend change, and the matrix cannot
   drift from the checks `require_permission` performs.

   Checkpoint 8: system templates (Admin/Manager/User) stay
   read-only, seeded by migration and shared by every tenant.
   A tenant's own custom roles can now be created, renamed,
   re-permissioned and deleted here — the backend still refuses
   all three for a system template. Assigning a role to a person
   is done on the Users screen.
   ============================================================ */

interface MatrixState {
  catalog: PermissionCatalog;
  roles: RoleDetail[];
}

interface RoleFormState {
  mode: 'create' | 'edit';
  roleId: string | null;
  name: string;
  description: string;
  permissions: Set<string>;
}

function emptyForm(): RoleFormState {
  return { mode: 'create', roleId: null, name: '', description: '', permissions: new Set() };
}

export default function AdminRolesPage() {
  const [state, setState] = useState<MatrixState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [form, setForm] = useState<RoleFormState | null>(null);
  const [formNameError, setFormNameError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const confirm = useConfirm();

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // The fetch is inline rather than a callback the effect invokes: state is
  // only ever assigned after an await, and a cancellation flag stops a late
  // response from painting over a newer one.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const matrix = await loadRoleMatrix();
        if (!cancelled) {
          setState(matrix);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setState(null);
          setError(describeApiError(caught, 'Could not load roles and permissions.'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const [activeRoleId, setActiveRoleId] = useState<string | null>(null);

  const openCreate = useCallback(() => {
    setFormNameError(null);
    setForm(emptyForm());
  }, []);

  const openEdit = useCallback((role: RoleDetail) => {
    setFormNameError(null);
    setForm({
      mode: 'edit',
      roleId: role.id,
      name: role.name,
      description: role.description ?? '',
      permissions: new Set(role.permissions),
    });
  }, []);

  const closeForm = useCallback(() => {
    if (saving) return;
    setForm(null);
  }, [saving]);

  const togglePermission = useCallback((code: string) => {
    setForm((current) => {
      if (current === null) return current;
      const next = new Set(current.permissions);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return { ...current, permissions: next };
    });
  }, []);

  const submitForm = useCallback(async () => {
    if (form === null) return;
    const name = form.name.trim();
    if (!name) {
      setFormNameError('A role needs a name.');
      return;
    }
    setFormNameError(null);
    setSaving(true);
    try {
      const payload = {
        name,
        description: form.description.trim() || null,
        permissions: Array.from(form.permissions),
      };
      if (form.mode === 'create') {
        await createRole(payload);
        notifySuccess(`"${name}" created.`);
      } else if (form.roleId) {
        await updateRole(form.roleId, payload);
        notifySuccess(`"${name}" updated.`);
      }
      setForm(null);
      reload();
    } catch (caught) {
      notifyError(caught, 'Could not save this role.');
    } finally {
      setSaving(false);
    }
  }, [form, reload]);

  const handleDelete = useCallback(
    async (role: RoleDetail) => {
      const result = await confirm({
        title: `Delete "${role.name}"?`,
        description:
          'This cannot be undone. Refused if the role is still assigned to any member — reassign them first.',
        tone: 'danger',
        confirmLabel: 'Delete role',
      });
      if (result === null) return;
      try {
        await deleteRole(role.id);
        notifySuccess(`"${role.name}" deleted.`);
        setActiveRoleId(null);
        reload();
      } catch (caught) {
        notifyError(caught, 'Could not delete this role.');
      }
    },
    [confirm, reload],
  );

  const header = (
    <div className="flex items-center justify-between gap-3.5">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-indigo-600">
          <Shield className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Roles &amp; Permissions</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            What each role may do, exactly as the API enforces it.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={openCreate}
        className="flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
        style={{ background: 'var(--accent)' }}
      >
        <Plus className="h-4 w-4" /> New role
      </button>
    </div>
  );

  if (error !== null) {
    return (
      <div className="mx-auto max-w-7xl space-y-5 p-6 lg:p-8">
        {header}
        <ListError message={error} onRetry={reload} />
      </div>
    );
  }

  if (state === null) {
    return (
      <div className="mx-auto max-w-7xl space-y-5 p-6 lg:p-8">
        {header}
        <div className="txt-muted flex items-center gap-2 py-10 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading the permission matrix…
        </div>
      </div>
    );
  }

  const { catalog, roles } = state;
  const active = roles.find((role) => role.id === activeRoleId) ?? roles[0] ?? null;

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 lg:p-8">
      {header}

      <PartialDataNotice>
        System templates (Admin, Manager, User) are read-only — seeded from the backend&rsquo;s
        permission catalogue and shared by every tenant. Your organization&rsquo;s own roles can be
        created, renamed, re-permissioned and deleted below; granting a role to a person is still
        done on the <strong>Users</strong> screen.
      </PartialDataNotice>

      {/* ---- Role selector ---- */}
      <div className="flex flex-wrap gap-2">
        {roles.map((role) => {
          const selected = active !== null && role.id === active.id;
          return (
            <button
              key={role.id}
              type="button"
              onClick={() => setActiveRoleId(role.id)}
              aria-pressed={selected}
              className={`bd flex items-center gap-2 rounded-xl border px-3.5 py-2 text-[13px] font-semibold transition ${
                selected ? 'surface-2 txt' : 'txt-muted hover:opacity-80'
              }`}
              style={selected ? { borderColor: 'var(--accent)' } : undefined}
            >
              {role.name}
              {role.is_system && <StatusBadge label="System" variant="neutral" />}
              <span className="txt-faint tabular-nums text-[11.5px]">
                {role.permissions.length}
              </span>
            </button>
          );
        })}
      </div>

      {active === null ? (
        <div className="surface bd rounded-2xl border p-10 text-center">
          <p className="txt text-[14px] font-semibold">No roles defined</p>
          <p className="txt-muted mt-1 text-[12.5px]">
            This organization has no roles, not even the seeded system templates.
          </p>
        </div>
      ) : (
        <div className="surface bd rounded-2xl border p-5">
          <div className="flex items-start justify-between gap-3">
            <SectionHeader title={`${active.name} — ${active.permissions.length} permissions`} />
            {!active.is_system && (
              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => openEdit(active)}
                  className="ctl bd flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
                >
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </button>
                <button
                  type="button"
                  onClick={() => void handleDelete(active)}
                  className="bd flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-semibold text-red-500 transition hover:opacity-80"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </button>
              </div>
            )}
          </div>
          {active.description && (
            <p className="txt-muted mt-1 text-[12.5px]">{active.description}</p>
          )}

          {/* Wide matrix scrolls inside its own container so the page never does. */}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse">
              <thead>
                <tr className="bd border-b">
                  <th className="txt-muted px-2 py-2.5 text-left text-[11px] font-bold uppercase tracking-wider">
                    Module
                  </th>
                  {catalog.actions.map((action) => (
                    <th
                      key={action}
                      className="txt-muted px-2 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider"
                    >
                      {humanize(action)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {catalog.modules.map((module) => (
                  <tr key={module} className="bd border-b last:border-0">
                    <td className="txt px-2 py-2.5 text-[12.5px] font-semibold">
                      {moduleLabel(module)}
                    </td>
                    {catalog.actions.map((action) => {
                      const granted = active.permissions.includes(`${module}.${action}`);
                      return (
                        <td key={action} className="px-2 py-2.5 text-center">
                          {granted ? (
                            <Check
                              className="mx-auto h-4 w-4 text-emerald-500"
                              aria-label="Granted"
                            />
                          ) : (
                            <X
                              className="txt-faint mx-auto h-4 w-4 opacity-40"
                              aria-label="Not granted"
                            />
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <SlideDrawer
        open={form !== null}
        onClose={closeForm}
        title={form?.mode === 'edit' ? 'Edit role' : 'New role'}
        subtitle={
          form?.mode === 'edit'
            ? 'Renaming or re-permissioning takes effect for everyone holding this role immediately.'
            : 'Custom roles are scoped to your organization only.'
        }
        footer={
          <>
            <button
              type="button"
              onClick={closeForm}
              disabled={saving}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold transition hover:opacity-80 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void submitForm()}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {saving && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {form?.mode === 'edit' ? 'Save changes' : 'Create role'}
            </button>
          </>
        }
      >
        {form !== null && (
          <div className="space-y-4">
            <FormField label="Name" required error={formNameError ?? undefined}>
              <FormInput
                autoFocus
                value={form.name}
                onChange={(event) =>
                  setForm((current) =>
                    current === null ? current : { ...current, name: event.target.value },
                  )
                }
                placeholder="e.g. Sales Lead"
                maxLength={64}
              />
            </FormField>

            <FormField label="Description" hint="Optional — shown to admins picking a role.">
              <FormTextarea
                value={form.description}
                rows={2}
                onChange={(event) =>
                  setForm((current) =>
                    current === null ? current : { ...current, description: event.target.value },
                  )
                }
              />
            </FormField>

            <div>
              <span className="txt block text-[13px] font-semibold">
                Permissions
                <span className="txt-faint ml-1.5 font-normal">
                  ({form.permissions.size} selected)
                </span>
              </span>
              <div className="bd mt-2 max-h-[360px] overflow-auto rounded-xl border">
                <table className="w-full min-w-[480px] border-collapse">
                  <thead className="sticky top-0 z-10">
                    <tr className="bd surface-2 border-b">
                      <th className="txt-muted px-2 py-2 text-left text-[10.5px] font-bold uppercase tracking-wider">
                        Module
                      </th>
                      {state?.catalog.actions.map((action) => (
                        <th
                          key={action}
                          className="txt-muted px-2 py-2 text-center text-[10.5px] font-bold uppercase tracking-wider"
                        >
                          {humanize(action)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {state?.catalog.modules.map((module) => (
                      <tr key={module} className="bd border-b last:border-0">
                        <td className="txt px-2 py-2 text-[12px] font-semibold">
                          {moduleLabel(module)}
                        </td>
                        {state.catalog.actions.map((action) => {
                          const code = `${module}.${action}`;
                          return (
                            <td key={action} className="px-2 py-2 text-center">
                              <input
                                type="checkbox"
                                checked={form.permissions.has(code)}
                                onChange={() => togglePermission(code)}
                                aria-label={code}
                                className="h-3.5 w-3.5 cursor-pointer accent-[var(--accent)]"
                              />
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </SlideDrawer>
    </div>
  );
}
