'use client';

import { useEffect, useRef, useState } from 'react';
import { Building2, Check, LogOut } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';

/* ============================================================
   ACCOUNT MENU
   Replaces the placeholder "U" avatar with the signed-in user,
   and carries the organization switcher and sign-out.

   With no backend configured it renders the original static
   avatar, so the demonstration build is unchanged.
   ============================================================ */

function initials(first?: string | null, last?: string | null, email?: string): string {
  const fromName = `${first?.[0] ?? ''}${last?.[0] ?? ''}`.trim();
  if (fromName) return fromName.toUpperCase();
  return (email?.[0] ?? 'U').toUpperCase();
}

export default function AccountMenu() {
  const { currentUser, memberships, activeOrganizationId, logout, switchOrganization } =
    useAuth();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  // Nothing to show until the session probe resolves. RequireAuth keeps this
  // brief: an unauthenticated visitor never reaches the CRM shell.
  if (!currentUser) {
    return (
      <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-[12px] font-bold text-white">
        U
      </div>
    );
  }

  const profile = currentUser.user.profile;
  const label = profile ? `${profile.first_name} ${profile.last_name}` : currentUser.user.email;
  const activeMembership = memberships.find(
    (membership) => membership.organization_id === activeOrganizationId,
  );

  const handleSwitch = async (organizationId: string) => {
    if (organizationId === activeOrganizationId) {
      setOpen(false);
      return;
    }
    setSwitching(true);
    try {
      await switchOrganization(organizationId);
      setOpen(false);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${label}`}
        className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-[12px] font-bold text-white transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
      >
        {initials(profile?.first_name, profile?.last_name, currentUser.user.email)}
      </button>

      {open && (
        <div
          role="menu"
          className="surface bd absolute right-0 top-full z-50 mt-2 w-[260px] overflow-hidden rounded-xl border shadow-[0_20px_50px_-20px_rgba(0,0,0,0.35)]"
        >
          {/* Identity */}
          <div className="bd border-b px-3.5 py-3">
            <p className="txt truncate text-[13px] font-semibold">{label}</p>
            <p className="txt-muted truncate text-[12px]">{currentUser.user.email}</p>
            {activeMembership && activeMembership.roles.length > 0 && (
              <p className="txt-faint mt-1 text-[11.5px] font-medium">
                {activeMembership.roles.join(', ')}
              </p>
            )}
          </div>

          {/* Organizations */}
          {memberships.length > 0 && (
            <div className="bd border-b py-1.5">
              <p className="txt-faint px-3.5 pb-1 pt-1 text-[10.5px] font-bold uppercase tracking-wider">
                Organization
              </p>
              {memberships.map((membership) => {
                const active = membership.organization_id === activeOrganizationId;
                return (
                  <button
                    key={membership.organization_id}
                    role="menuitem"
                    type="button"
                    disabled={switching || membership.status !== 'ACTIVE'}
                    onClick={() => void handleSwitch(membership.organization_id)}
                    className={cn(
                      'flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-[12.5px] font-medium transition-colors',
                      'hover:surface-2 disabled:cursor-not-allowed disabled:opacity-50',
                    )}
                  >
                    <Building2
                      className="h-3.5 w-3.5 shrink-0"
                      style={{ color: 'var(--accent)' }}
                      aria-hidden="true"
                    />
                    <span className="txt min-w-0 flex-1 truncate">
                      {membership.organization_name}
                    </span>
                    {active && (
                      <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden="true" />
                    )}
                  </button>
                );
              })}
            </div>
          )}

          <button
            role="menuitem"
            type="button"
            onClick={() => void logout()}
            className="hover:surface-2 flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[12.5px] font-medium text-red-500 transition-colors"
          >
            <LogOut className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
