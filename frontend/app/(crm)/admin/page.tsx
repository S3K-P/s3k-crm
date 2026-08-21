'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Blocks, Building2, Loader2, ScrollText, Shield, UsersRound, Workflow } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { usePermissions } from '@/context/AuthContext';
import { getCurrentOrganization, listMembers, type OrganizationSummary } from '@/features/admin/users';
import { listRoles, type Role } from '@/features/admin/roles';
import { listStages, type PipelineStage } from '@/features/crm/opportunities';

/* ============================================================
   ADMIN OVERVIEW

   Every number on this page is counted from a real API response.

   What used to be here: "1,245 total users", "99.9% system
   health", "12ms database latency", "62% storage capacity" — all
   invented, none measured, and none distinguishable from a real
   reading by anyone looking at the screen. They are gone. There
   is no telemetry backend, so the page does not claim one.
   ============================================================ */

interface Counts {
  members: number;
  activeMembers: number;
  roles: number;
  stages: number;
}

function StatCard({
  label,
  value,
  href,
  icon: Icon,
  tint,
}: {
  label: string;
  value: string;
  href?: string;
  icon: typeof UsersRound;
  tint: string;
}) {
  const body = (
    <div className="surface bd flex items-start gap-4 rounded-xl border p-5 transition hover:border-[var(--accent)]">
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
        style={{ background: 'var(--surface-2)' }}
      >
        <Icon className={`h-5 w-5 ${tint}`} />
      </div>
      <div>
        <p className="txt-muted text-[11px] font-bold uppercase tracking-wider">{label}</p>
        <p className="font-display txt mt-1 text-[24px] font-bold leading-none tabular-nums">
          {value}
        </p>
      </div>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function AdminDashboardPage() {
  const { can } = usePermissions();
  const mayViewUsers = can('users', 'VIEW');
  const mayViewRoles = can('roles', 'VIEW');
  const mayViewOpportunities = can('opportunities', 'VIEW');

  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const next: Counts = { members: 0, activeMembers: 0, roles: 0, stages: 0 };
      const problems: string[] = [];

      try {
        const org = await getCurrentOrganization();
        if (!cancelled) setOrganization(org);
      } catch (caught) {
        problems.push(describeApiError(caught, 'organization'));
      }

      if (mayViewUsers) {
        try {
          const page = await listMembers();
          next.members = page.total;
          next.activeMembers = page.data.filter((m) => m.status === 'ACTIVE').length;
        } catch {
          problems.push('members');
        }
      }
      if (mayViewRoles) {
        try {
          const roles: Role[] = await listRoles();
          next.roles = roles.length;
        } catch {
          problems.push('roles');
        }
      }
      if (mayViewOpportunities) {
        try {
          const stages: PipelineStage[] = await listStages();
          next.stages = stages.length;
        } catch {
          problems.push('pipeline stages');
        }
      }

      if (!cancelled) {
        setCounts(next);
        setError(problems.length > 0 ? `Could not load: ${problems.join(', ')}.` : null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayViewUsers, mayViewRoles, mayViewOpportunities]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col space-y-6 p-6 lg:p-8">
      <div>
        <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
          Administration
        </h1>
        <p className="txt-muted mt-1 text-[13.5px]">
          {organization ? (
            <>
              Configuration for <strong>{organization.name}</strong>.
            </>
          ) : (
            'Configuration for the organization you are signed in to.'
          )}
        </p>
      </div>

      {error !== null && (
        <p role="alert" className="text-[12.5px] font-medium text-red-500">
          {error}
        </p>
      )}

      {counts === null ? (
        <div className="txt-muted flex items-center gap-2 py-6 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Counting…
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard
            label="Members"
            value={String(counts.members)}
            href={mayViewUsers ? '/admin/users' : undefined}
            icon={UsersRound}
            tint="text-sky-500"
          />
          <StatCard
            label="Active members"
            value={String(counts.activeMembers)}
            href={mayViewUsers ? '/admin/users' : undefined}
            icon={Shield}
            tint="text-emerald-500"
          />
          <StatCard
            label="Roles"
            value={String(counts.roles)}
            href={mayViewRoles ? '/admin/roles' : undefined}
            icon={Workflow}
            tint="text-violet-500"
          />
          <StatCard
            label="Pipeline stages"
            value={String(counts.stages)}
            href={mayViewOpportunities ? '/admin/crm-settings' : undefined}
            icon={Building2}
            tint="text-amber-500"
          />
        </div>
      )}

      <div className="surface bd rounded-2xl border p-5">
        <SectionHeader title="Administration areas" />
        <div className="grid gap-3 pt-4 sm:grid-cols-2">
          <Link
            href="/admin/users"
            className="bd flex items-center gap-3 rounded-xl border p-3.5 transition hover:border-[var(--accent)]"
          >
            <UsersRound className="txt-muted h-4 w-4 shrink-0" />
            <div>
              <p className="txt text-[13px] font-semibold">Users</p>
              <p className="txt-muted text-[11.5px]">Membership and role assignment</p>
            </div>
          </Link>
          <Link
            href="/admin/roles"
            className="bd flex items-center gap-3 rounded-xl border p-3.5 transition hover:border-[var(--accent)]"
          >
            <Shield className="txt-muted h-4 w-4 shrink-0" />
            <div>
              <p className="txt text-[13px] font-semibold">Roles &amp; permissions</p>
              <p className="txt-muted text-[11.5px]">The enforced permission matrix</p>
            </div>
          </Link>
          <Link
            href="/admin/crm-settings"
            className="bd flex items-center gap-3 rounded-xl border p-3.5 transition hover:border-[var(--accent)]"
          >
            <Blocks className="txt-muted h-4 w-4 shrink-0" />
            <div>
              <p className="txt text-[13px] font-semibold">CRM settings</p>
              <p className="txt-muted text-[11.5px]">Pipeline stages and lead sources</p>
            </div>
          </Link>
          <Link
            href="/admin/audit-logs"
            className="bd flex items-center gap-3 rounded-xl border p-3.5 transition hover:border-[var(--accent)]"
          >
            <ScrollText className="txt-muted h-4 w-4 shrink-0" />
            <div>
              <p className="txt text-[13px] font-semibold">Audit logs</p>
              <p className="txt-muted text-[11.5px]">Not yet available</p>
            </div>
          </Link>
        </div>
      </div>

      <PartialDataNotice>
        System telemetry — uptime, database latency, storage and API usage — is not shown because
        nothing measures it yet. The counts above are the only figures this deployment can report
        truthfully.
      </PartialDataNotice>
    </div>
  );
}
