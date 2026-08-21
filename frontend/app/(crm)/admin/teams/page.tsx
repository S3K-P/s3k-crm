'use client';

import Link from 'next/link';
import { UsersRound } from 'lucide-react';

import NotConfigured from '@/components/crm/shared/NotConfigured';

/* ============================================================
   ADMIN — TEAMS

   Departments and teams are not modelled. There are no
   `platform.departments`, `platform.teams` or
   `platform.team_memberships` tables, so a team has nowhere to
   exist and no member can belong to one.

   Roles are granted per organization membership today, which is
   what actually governs access — so the Users and Roles screens
   are where administration happens until teams are built.
   ============================================================ */

export default function AdminTeamsPage() {
  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-500 to-purple-600">
          <UsersRound className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Teams</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            Departments, teams and their membership.
          </p>
        </div>
      </div>

      <NotConfigured
        title="Teams are not modelled yet"
        description="There is no team or department table in the database, so no team can be created and no one can be assigned to one. Access today is governed entirely by the roles held on an organization membership."
        requires="platform.departments, platform.teams, platform.team_memberships"
      />

      <p className="txt-muted text-center text-[12.5px]">
        Manage access on{' '}
        <Link href="/admin/users" className="font-semibold hover:underline" style={{ color: 'var(--accent)' }}>
          Users
        </Link>{' '}
        and{' '}
        <Link href="/admin/roles" className="font-semibold hover:underline" style={{ color: 'var(--accent)' }}>
          Roles &amp; Permissions
        </Link>
        .
      </p>
    </div>
  );
}
