'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Building2, Loader2, Plus, Trash2, UserPlus, UsersRound, X } from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  addTeamMember,
  createDepartment,
  createTeam,
  deleteDepartment,
  deleteTeam,
  listDepartments,
  listTeamMembers,
  listTeams,
  removeTeamMember,
  TEAM_WINDOW,
  type Department,
  type Team,
  type TeamMember,
} from '@/features/admin/teams';
import {
  listMembers,
  MEMBER_WINDOW,
  type OrganizationMember,
} from '@/features/admin/users';

/* ============================================================
   ADMIN — TEAMS

   Departments, teams and their membership, backed by
   `/api/v1/teams` and `/api/v1/departments`.

   Membership is an authorization control, not a label: a user
   holding `<module>.VIEW_TEAM` can read records owned by anyone
   on a team they share. Adding somebody therefore widens what
   they can see, which is why removal confirms and why every
   change is audited server-side.

   Permissions decide which controls render; the backend
   re-checks every one of them, so a hidden button is a courtesy
   and a forged request is a 403.
   ============================================================ */

export default function AdminTeamsPage() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayView = can('teams', 'VIEW');
  const mayCreate = can('teams', 'CREATE');
  const mayEdit = can('teams', 'EDIT');
  const mayDelete = can('teams', 'DELETE');

  const [teams, setTeams] = useState<Team[] | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [people, setPeople] = useState<OrganizationMember[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [teamName, setTeamName] = useState('');
  const [teamDepartment, setTeamDepartment] = useState('');
  const [departmentName, setDepartmentName] = useState('');
  const [busy, setBusy] = useState(false);

  const [openTeam, setOpenTeam] = useState<Team | null>(null);

  const reload = useCallback(() => setReloadToken((n) => n + 1), []);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;

    void (async () => {
      try {
        const [teamPage, departmentPage] = await Promise.all([
          listTeams({ page_size: TEAM_WINDOW }),
          listDepartments({ page_size: TEAM_WINDOW }),
        ]);
        if (cancelled) return;
        setTeams(teamPage.data);
        setDepartments(departmentPage.data);
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setTeams([]);
        setError(describeApiError(caught, 'Teams could not be loaded.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayView, reloadToken]);

  // The member list backs the "add to team" picker. Fetched once and
  // separately: a failure here must not blank the teams themselves.
  useEffect(() => {
    if (!mayEdit) return;
    let cancelled = false;
    void (async () => {
      try {
        const page = await listMembers({ limit: MEMBER_WINDOW });
        if (!cancelled) setPeople(page.data);
      } catch {
        /* the picker degrades to empty; teams still render */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayEdit]);

  if (!mayView) {
    return (
      <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
        <Header />
        <p className="txt-muted text-[13px]">
          You do not have permission to view teams.
        </p>
      </div>
    );
  }

  const handleCreateTeam = async () => {
    const name = teamName.trim();
    if (!name) return;
    setBusy(true);
    try {
      await createTeam({
        name,
        department_id: teamDepartment === '' ? null : teamDepartment,
      });
      notifySuccess('Team created', name);
      setTeamName('');
      setTeamDepartment('');
      reload();
    } catch (caught) {
      notifyError(caught, 'The team could not be created.');
    } finally {
      setBusy(false);
    }
  };

  const handleCreateDepartment = async () => {
    const name = departmentName.trim();
    if (!name) return;
    setBusy(true);
    try {
      await createDepartment({ name });
      notifySuccess('Department created', name);
      setDepartmentName('');
      reload();
    } catch (caught) {
      notifyError(caught, 'The department could not be created.');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteTeam = async (team: Team) => {
    const ok = await confirm({
      title: 'Delete this team?',
      description: (
        <>
          <strong>{team.name}</strong> will be removed along with its{' '}
          {team.member_count} member{team.member_count === 1 ? '' : 's'}. Anyone who
          could see a team-mate&apos;s records through it will lose that access.
        </>
      ),
      confirmLabel: 'Delete team',
      tone: 'danger',
    });
    if (!ok) return;

    try {
      await deleteTeam(team.id);
      notifySuccess('Team deleted', team.name);
      if (openTeam?.id === team.id) setOpenTeam(null);
      reload();
    } catch (caught) {
      notifyError(caught, 'The team could not be deleted.');
    }
  };

  const handleDeleteDepartment = async (department: Department) => {
    const ok = await confirm({
      title: 'Delete this department?',
      description: (
        <>
          <strong>{department.name}</strong> will be removed. Teams must be moved out
          of it first.
        </>
      ),
      confirmLabel: 'Delete department',
      tone: 'danger',
    });
    if (!ok) return;

    try {
      await deleteDepartment(department.id);
      notifySuccess('Department deleted', department.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The department could not be deleted.');
    }
  };

  const departmentName_ = (id: string | null) =>
    departments.find((d) => d.id === id)?.name ?? null;

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <Header />

      {error !== null ? (
        <div className="surface bd rounded-2xl border p-5">
          <p role="alert" className="text-[13px] font-medium text-red-500">
            {error}
          </p>
          <button
            type="button"
            onClick={reload}
            className="ctl bd mt-3 rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
          >
            Try again
          </button>
        </div>
      ) : null}

      {/* --- Departments --- */}
      <section className="surface bd rounded-2xl border p-5">
        <div className="flex items-center gap-2">
          <Building2 className="txt-faint h-4 w-4" aria-hidden="true" />
          <h2 className="txt text-[15px] font-bold">Departments</h2>
        </div>
        <p className="txt-muted mt-1 text-[12.5px]">
          Optional grouping above teams. Departments carry no access of their own.
        </p>

        {mayCreate ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              value={departmentName}
              onChange={(event) => setDepartmentName(event.target.value)}
              placeholder="Department name"
              maxLength={160}
              className="ctl bd min-w-[200px] flex-1 rounded-lg border px-3 py-1.5 text-[13px]"
            />
            <button
              type="button"
              onClick={() => void handleCreateDepartment()}
              disabled={busy || departmentName.trim() === ''}
              className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add
            </button>
          </div>
        ) : null}

        {departments.length === 0 ? (
          <p className="txt-faint mt-3 text-[12.5px]">No departments yet.</p>
        ) : (
          <ul className="mt-3 flex flex-wrap gap-2">
            {departments.map((department) => (
              <li
                key={department.id}
                className="ctl bd inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-[12.5px]"
              >
                {department.name}
                {mayDelete ? (
                  <button
                    type="button"
                    onClick={() => void handleDeleteDepartment(department)}
                    aria-label={`Delete ${department.name}`}
                    className="txt-faint transition hover:text-red-500"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* --- Teams --- */}
      <section className="surface bd rounded-2xl border p-5">
        <div className="flex items-center gap-2">
          <UsersRound className="txt-faint h-4 w-4" aria-hidden="true" />
          <h2 className="txt text-[15px] font-bold">Teams</h2>
        </div>
        <p className="txt-muted mt-1 text-[12.5px]">
          Members of a team can read one another&apos;s records where their role
          grants <code className="text-[11.5px]">VIEW_TEAM</code>. Grant that on{' '}
          <Link
            href="/admin/roles"
            className="font-semibold hover:underline"
            style={{ color: 'var(--accent)' }}
          >
            Roles &amp; Permissions
          </Link>
          .
        </p>

        {mayCreate ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              value={teamName}
              onChange={(event) => setTeamName(event.target.value)}
              placeholder="Team name"
              maxLength={160}
              className="ctl bd min-w-[200px] flex-1 rounded-lg border px-3 py-1.5 text-[13px]"
            />
            <select
              value={teamDepartment}
              onChange={(event) => setTeamDepartment(event.target.value)}
              className="ctl bd rounded-lg border px-3 py-1.5 text-[13px]"
              aria-label="Department"
            >
              <option value="">No department</option>
              {departments.map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void handleCreateTeam()}
              disabled={busy || teamName.trim() === ''}
              className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add team
            </button>
          </div>
        ) : null}

        <div className="mt-4">
          {teams === null ? (
            <p className="txt-muted flex items-center gap-2 py-4 text-[12.5px]">
              <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" /> Loading…
            </p>
          ) : teams.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <UsersRound className="txt-faint h-5 w-5" aria-hidden="true" />
              <p className="txt-muted text-[12.5px]">
                No teams yet
                {mayCreate ? '. Create one to group people who share a pipeline.' : '.'}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-[var(--border)]">
              {teams.map((team) => (
                <li key={team.id} className="flex items-center gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="txt truncate text-[13px] font-medium">{team.name}</p>
                    <p className="txt-faint text-[11.5px]">
                      {team.member_count} member{team.member_count === 1 ? '' : 's'}
                      {departmentName_(team.department_id)
                        ? ` · ${departmentName_(team.department_id)}`
                        : ''}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => setOpenTeam(openTeam?.id === team.id ? null : team)}
                    className="ctl bd rounded-lg border px-2.5 py-1 text-[12px] font-semibold transition hover:opacity-80"
                  >
                    {openTeam?.id === team.id ? 'Hide' : 'Members'}
                  </button>

                  {mayDelete ? (
                    <button
                      type="button"
                      onClick={() => void handleDeleteTeam(team)}
                      aria-label={`Delete ${team.name}`}
                      className="ctl grid h-7 w-7 shrink-0 place-items-center rounded-lg text-red-500 transition hover:opacity-80"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {openTeam ? (
        <TeamMembersPanel
          team={openTeam}
          people={people}
          mayEdit={mayEdit}
          onChanged={reload}
        />
      ) : null}
    </div>
  );
}

function Header() {
  return (
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
  );
}

interface MembersPanelProps {
  team: Team;
  people: OrganizationMember[];
  mayEdit: boolean;
  onChanged: () => void;
}

function TeamMembersPanel({ team, people, mayEdit, onChanged }: MembersPanelProps) {
  const confirm = useConfirm();
  const [members, setMembers] = useState<TeamMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const page = await listTeamMembers(team.id, { page_size: TEAM_WINDOW });
        if (!cancelled) {
          setMembers(page.data);
          setError(null);
        }
      } catch (caught) {
        if (cancelled) return;
        setMembers([]);
        setError(describeApiError(caught, 'Members could not be loaded.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [team.id, token]);

  const nameFor = (userId: string) => {
    const person = people.find((p) => p.user_id === userId);
    return person?.full_name?.trim() || person?.email || userId;
  };

  const onTeam = new Set((members ?? []).map((m) => m.user_id));
  const addable = people.filter((person) => !onTeam.has(person.user_id));

  const handleAdd = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await addTeamMember(team.id, selected);
      notifySuccess('Member added', nameFor(selected));
      setSelected('');
      setToken((n) => n + 1);
      onChanged();
    } catch (caught) {
      notifyError(caught, 'The member could not be added.');
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (member: TeamMember) => {
    const who = nameFor(member.user_id);
    const ok = await confirm({
      title: 'Remove from this team?',
      description: (
        <>
          <strong>{who}</strong> will leave <strong>{team.name}</strong> and will no
          longer see records owned by its other members.
        </>
      ),
      confirmLabel: 'Remove',
      tone: 'danger',
    });
    if (!ok) return;

    try {
      await removeTeamMember(team.id, member.user_id);
      notifySuccess('Member removed', who);
      setToken((n) => n + 1);
      onChanged();
    } catch (caught) {
      notifyError(caught, 'The member could not be removed.');
    }
  };

  return (
    <section className="surface bd rounded-2xl border p-5">
      <h2 className="txt text-[15px] font-bold">{team.name} — members</h2>

      {mayEdit ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
            className="ctl bd min-w-[220px] flex-1 rounded-lg border px-3 py-1.5 text-[13px]"
            aria-label="Person to add"
          >
            <option value="">Select a person…</option>
            {addable.map((person) => (
              <option key={person.user_id} value={person.user_id}>
                {person.full_name?.trim() || person.email}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={busy || selected === ''}
            className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <UserPlus className="h-3.5 w-3.5" aria-hidden="true" /> Add
          </button>
        </div>
      ) : null}

      <div className="mt-3">
        {error !== null ? (
          <p role="alert" className="text-[12.5px] font-medium text-red-500">
            {error}
          </p>
        ) : members === null ? (
          <p className="txt-muted flex items-center gap-2 py-3 text-[12.5px]">
            <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" /> Loading…
          </p>
        ) : members.length === 0 ? (
          <p className="txt-faint py-3 text-[12.5px]">Nobody is on this team yet.</p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {members.map((member) => (
              <li key={member.id} className="flex items-center gap-3 py-2">
                <span className="txt min-w-0 flex-1 truncate text-[13px]">
                  {nameFor(member.user_id)}
                </span>
                {mayEdit ? (
                  <button
                    type="button"
                    onClick={() => void handleRemove(member)}
                    aria-label={`Remove ${nameFor(member.user_id)}`}
                    className="ctl grid h-7 w-7 shrink-0 place-items-center rounded-lg text-red-500 transition hover:opacity-80"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
