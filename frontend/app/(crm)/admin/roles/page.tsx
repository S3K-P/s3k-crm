'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, Shield, X } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize } from '@/components/crm/shared/statusVariants';
import { ListError } from '@/components/crm/shared/ListStates';
import { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  loadRoleMatrix,
  moduleLabel,
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

   The matrix is read-only: there is no endpoint for editing a
   role's permissions. Assigning a role to a person is done on
   the Users screen.
   ============================================================ */

interface MatrixState {
  catalog: PermissionCatalog;
  roles: RoleDetail[];
}

export default function AdminRolesPage() {
  const [state, setState] = useState<MatrixState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

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

  const header = (
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
        This matrix is read-only. Role permissions are seeded from the backend&rsquo;s permission
        catalogue and there is no endpoint for editing them; granting a role to a person is done on
        the <strong>Users</strong> screen.
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
          <SectionHeader title={`${active.name} — ${active.permissions.length} permissions`} />
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
    </div>
  );
}
