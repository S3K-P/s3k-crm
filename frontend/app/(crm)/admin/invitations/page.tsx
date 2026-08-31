'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Loader2, Mail, Send, X } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { listRoles, type Role } from '@/features/admin/roles';
import { api, ApiError } from '@/lib/api-client';
import type { Invitation, InvitationCreated } from '@/features/platform/types';

/* ============================================================
   ADMIN → ACCESS MANAGEMENT → INVITATIONS

   Invite somebody to join this organization, and manage the
   invitations already outstanding.

   **Why there is a "Copy link" button rather than "Resend
   email".** This deployment has no email backend — the
   notifications module is an unimplemented Phase 0 placeholder —
   so the administrator passes the link on themselves. Showing a
   "Sent!" confirmation for a message nothing will deliver would
   be exactly the fake functionality this work is not allowed to
   ship. The link is composed here, against this page's own
   origin, so it is correct in whatever environment it is served
   from.

   The token is shown **once**, on creation, and is never
   returned by the listing. An administrator who navigates away
   before copying it revokes and re-invites; there is no way to
   recover it, by design.
   ============================================================ */

export default function AdminInvitationsPage() {
  const { can } = usePermissions();
  const mayInvite = can('users', 'CREATE');
  const mayView = can('users', 'VIEW');

  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [email, setEmail] = useState('');
  const [roleId, setRoleId] = useState('');
  const [sending, setSending] = useState(false);

  /** The most recently created invitation's link, shown once. */
  const [freshLink, setFreshLink] = useState<{ email: string; url: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [working, setWorking] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!mayView) return;
    try {
      const [items, roleList] = await Promise.all([
        api.get<Invitation[]>('/organizations/current/invitations'),
        listRoles(),
      ]);
      setInvitations(items);
      setRoles(roleList);
      setLoadError(null);
    } catch (caught) {
      setLoadError(
        caught instanceof ApiError ? caught.message : 'Unable to load invitations.',
      );
    }
  }, [mayView]);

  // Async IIFE inside the effect, as `useCollection` does: calling an async
  // state-setting function directly trips `react-hooks/set-state-in-effect`.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (cancelled) return;
      await load();
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const invite = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (sending) return;
    setSending(true);
    setCopied(false);
    try {
      const created = await api.post<InvitationCreated>(
        '/organizations/current/invitations',
        { email: email.trim(), role_id: roleId || null },
      );
      // Composed here rather than by the API: only the browser knows the
      // origin the invitee should be sent to.
      setFreshLink({
        email: created.invitation.email,
        url: `${window.location.origin}/invitations/accept?token=${encodeURIComponent(created.token)}`,
      });
      setEmail('');
      setRoleId('');
      notifySuccess('Invitation created', 'Copy the link and send it to them.');
      await load();
    } catch (caught) {
      notifyError(caught, 'Unable to create that invitation.');
    } finally {
      setSending(false);
    }
  };

  const revoke = async (invitation: Invitation) => {
    setWorking(invitation.id);
    try {
      await api.post(
        `/organizations/current/invitations/${invitation.id}/revoke`,
      );
      // Any link already sent for this invitation stops working immediately.
      if (freshLink?.email === invitation.email) setFreshLink(null);
      notifySuccess('Invitation revoked');
      await load();
    } catch (caught) {
      notifyError(caught, 'Unable to revoke that invitation.');
    } finally {
      setWorking(null);
    }
  };

  const copy = async () => {
    if (!freshLink) return;
    try {
      await navigator.clipboard.writeText(freshLink.url);
      setCopied(true);
    } catch {
      // A blocked clipboard is not a failure worth an error toast — the link
      // is on screen and selectable.
      setCopied(false);
    }
  };

  if (!mayView) {
    return (
      <div className="p-6 lg:p-8">
        <p className="txt-muted text-[13px]">
          You do not have permission to view invitations.
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="font-display txt text-[22px] font-extrabold tracking-tight">
          Invitations
        </h1>
        <p className="txt-muted mt-1 text-[13px]">
          Invite people to join this organization. They keep their own S3K
          account and sign in with their own password.
        </p>
      </div>

      {mayInvite && (
        <form onSubmit={invite} className="surface bd mb-7 rounded-xl border p-5">
          <SectionHeader title="Invite a team member" />
          <div className="grid gap-4 sm:grid-cols-[1fr_14rem_auto] sm:items-end">
            <div className="space-y-1.5">
              <label htmlFor="invite_email" className="txt text-[13px] font-semibold">
                Email
              </label>
              <div className="relative">
                <Mail
                  className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
                  aria-hidden="true"
                />
                <input
                  id="invite_email"
                  type="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={sending}
                  className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)]"
                  placeholder="colleague@company.com"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="invite_role" className="txt text-[13px] font-semibold">
                Role
              </label>
              <select
                id="invite_role"
                value={roleId}
                onChange={(event) => setRoleId(event.target.value)}
                disabled={sending}
                className="ctl w-full px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]"
              >
                <option value="">No role</option>
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={sending || !email.trim()}
              className="flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {sending ? (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
              ) : (
                <Send className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              Create invitation
            </button>
          </div>

          {/* Shown once. The token is not recoverable afterwards. */}
          {freshLink && (
            <div
              className="mt-5 rounded-xl p-4"
              style={{ background: 'var(--accent-soft)' }}
            >
              <p className="txt text-[13px] font-semibold">
                Invitation link for {freshLink.email}
              </p>
              <p className="txt-muted mt-0.5 text-[12px]">
                This link is shown only once. Send it to them — S3K does not send
                the email itself in this deployment.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <code className="surface bd txt min-w-0 flex-1 truncate rounded-lg border px-3 py-2 text-[11.5px]">
                  {freshLink.url}
                </code>
                <button
                  type="button"
                  onClick={() => void copy()}
                  className="bd txt flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {copied ? 'Copied' : 'Copy link'}
                </button>
              </div>
            </div>
          )}
        </form>
      )}

      <SectionHeader title="Outstanding invitations" />

      {loadError && (
        <p role="alert" className="text-[13px] font-medium text-red-500">
          {loadError}
        </p>
      )}

      {invitations === null && !loadError && (
        <p className="txt-muted flex items-center gap-2 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          Loading invitations…
        </p>
      )}

      {invitations?.length === 0 && (
        <p className="txt-muted text-[13px]">
          No invitations yet. Invite somebody above to get started.
        </p>
      )}

      {invitations && invitations.length > 0 && (
        <ul className="space-y-2.5">
          {invitations.map((invitation) => (
            <li
              key={invitation.id}
              className="surface bd flex flex-wrap items-center gap-4 rounded-xl border p-4"
            >
              <div className="min-w-[14rem] flex-1">
                <p className="txt text-[13.5px] font-semibold">{invitation.email}</p>
                <p className="txt-muted text-[12px]">
                  {invitation.status === 'ACCEPTED'
                    ? `Joined ${new Date(invitation.accepted_at ?? invitation.created_at).toLocaleDateString()}`
                    : `Expires ${new Date(invitation.expires_at).toLocaleDateString()}`}
                </p>
              </div>

              <span className="status-badge shrink-0 text-[10.5px] font-bold uppercase tracking-wider">
                {invitation.status}
              </span>

              {invitation.status === 'PENDING' && mayInvite && (
                <button
                  type="button"
                  onClick={() => void revoke(invitation)}
                  disabled={working !== null}
                  className="bd txt flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:opacity-50"
                >
                  {working === invitation.id ? (
                    <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
                  ) : (
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
