'use client';

import { Check, Lock, Minus } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import NotConfigured from '@/components/crm/shared/NotConfigured';

/* ============================================================
   ADMIN — SECURITY

   This page states which authentication protections are actually
   in force, and which are not.

   It previously showed an MFA toggle rendered in the "on"
   position. Multi-factor authentication is not implemented
   anywhere in this system — no enrolment, no challenge, no
   recovery codes. A security page that claims MFA is enabled
   when it does not exist is the most dangerous kind of dummy
   data in the application, which is why it is gone rather than
   merely greyed out.

   The items marked active below are enforced by the backend and
   covered by tests; the values match `app/core/config.py`
   defaults. A deployment that overrides them will differ, which
   is why no figure here is presented as a live reading.
   ============================================================ */

interface Control {
  name: string;
  detail: string;
  active: boolean;
}

/** Enforced today, per the auth service and its default settings. */
const IN_FORCE: Control[] = [
  {
    name: 'Password hashing (argon2)',
    detail: 'Passwords are stored as argon2 digests, never reversibly.',
    active: true,
  },
  {
    name: 'Password length policy',
    detail: 'Minimum 12 characters, enforced on registration and change.',
    active: true,
  },
  {
    name: 'Brute-force lockout',
    detail: 'The account locks for 15 minutes after 5 consecutive failures.',
    active: true,
  },
  {
    name: 'Short-lived access tokens',
    detail: 'Ed25519-signed, 15-minute lifetime, held in memory only.',
    active: true,
  },
  {
    name: 'Refresh token rotation',
    detail: 'httpOnly cookie; every use issues a new token and retires the old one.',
    active: true,
  },
  {
    name: 'Stolen-token detection',
    detail: 'Replaying a retired refresh token revokes its entire family.',
    active: true,
  },
  {
    name: 'Tenant isolation',
    detail: 'Row-level security in PostgreSQL, plus an organization filter on every query.',
    active: true,
  },
];

/** Not built. Listed so their absence is explicit rather than assumed. */
const NOT_IN_FORCE: Control[] = [
  {
    name: 'Multi-factor authentication',
    detail: 'Not implemented. There is no enrolment, challenge or recovery flow.',
    active: false,
  },
  {
    name: 'Password reset and email verification',
    detail: 'Not implemented. There is no email transport configured.',
    active: false,
  },
  {
    name: 'Single sign-on (SAML / OIDC)',
    detail: 'Not implemented.',
    active: false,
  },
  {
    name: 'API rate limiting',
    detail: 'Not implemented. Only login lockout limits repeated requests.',
    active: false,
  },
  {
    name: 'Audit trail',
    detail: 'Not implemented. Security events are not recorded anywhere.',
    active: false,
  },
];

function ControlRow({ control }: { control: Control }) {
  return (
    <div
      className="bd flex items-start gap-3 rounded-xl border p-3"
      style={{ background: 'var(--surface-2)' }}
    >
      {control.active ? (
        <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" aria-label="In force" />
      ) : (
        <Minus className="txt-faint mt-0.5 h-4 w-4 shrink-0" aria-label="Not in force" />
      )}
      <div>
        <p className={`text-[13px] font-semibold ${control.active ? 'txt' : 'txt-muted'}`}>
          {control.name}
        </p>
        <p className="txt-muted mt-0.5 text-[11.5px] leading-relaxed">{control.detail}</p>
      </div>
    </div>
  );
}

export default function AdminSecurityPage() {
  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-zinc-700 to-black">
          <Lock className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Security</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            Which authentication protections are in force.
          </p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="In force" />
          <div className="mt-4 space-y-2.5">
            {IN_FORCE.map((control) => (
              <ControlRow key={control.name} control={control} />
            ))}
          </div>
        </div>

        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Not implemented" />
          <div className="mt-4 space-y-2.5">
            {NOT_IN_FORCE.map((control) => (
              <ControlRow key={control.name} control={control} />
            ))}
          </div>
        </div>
      </div>

      <p className="txt-faint text-[11.5px] leading-relaxed">
        These are the defaults from the backend configuration. They describe what the software
        enforces, not a live reading from this deployment — there is no settings API to query, so a
        deployment that overrides a value will differ from what is shown here.
      </p>

      <NotConfigured
        compact
        title="Billing and subscription are not available"
        description="This system has no billing, plan or subscription model. Nothing is metered and no plan is in effect."
        requires="Billing service (not planned in the current roadmap)"
      />
    </div>
  );
}
