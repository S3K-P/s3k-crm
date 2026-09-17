'use client';

import { useState } from 'react';
import { KeyRound } from 'lucide-react';

/* ============================================================
   DEV CREDENTIALS — TEMPORARY, DEVELOPMENT ONLY

   The three seeded sign-ins, one per system role, so the CRM
   can be exercised without looking them up. Clicking one fills
   the form; it does not submit, so the normal sign-in path is
   still what runs.

   ── KEEP IN SYNC ───────────────────────────────────────────
   These are provisioned by `backend/scripts/seed-dev-accounts.sh`,
   which is the source of truth. The addresses and the password
   are FIXED — they are re-provisioned to the same values on
   every run, so nothing here needs updating when the database
   is rebuilt. Change one side and you must change the other.

   ── TO REMOVE ──────────────────────────────────────────────
   Delete this file and the two lines that use it in
   `app/login/page.tsx` (the import and `<DevCredentials …/>`).
   Nothing else references it.

   ── WHAT THE PRODUCTION GUARD ACTUALLY GIVES YOU ───────────
   `process.env.NODE_ENV` is inlined by Next at build time, so
   the early return is statically true in a production build and
   the panel can never render. The browser bundle is clean, but
   the strings DO survive in the emitted server-side `.js.map`.
   Source maps are not served to browsers, yet they exist on
   disk in a build.

   So the real protection is that these accounts exist only in
   the local development database and are provisioned nowhere
   else. Treat the guard as defence in depth, not as permission
   to leave this in. **Delete it before anything ships.**
   ============================================================ */

interface DemoAccount {
  role: string;
  email: string;
  /** What this role can actually do, so the right one gets picked. */
  hint: string;
}

/** Fixed. Mirrors `backend/scripts/seed-dev-accounts.sh`. */
const PASSWORD = 'DemoPassw0rd!2026';

const ACCOUNTS: DemoAccount[] = [
  { role: 'Admin', email: 'admin@demo.example', hint: 'everything, incl. admin screens' },
  { role: 'Manager', email: 'manager@demo.example', hint: 'all CRM records, may delete' },
  { role: 'User', email: 'user@demo.example', hint: 'own records only' },
];

export default function DevCredentials({
  onPick,
}: {
  onPick: (email: string, password: string) => void;
}) {
  const [open, setOpen] = useState(false);

  if (process.env.NODE_ENV === 'production') return null;

  return (
    <div className="bd mt-4 rounded-lg border border-dashed p-3">
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        aria-expanded={open}
        className="txt-muted flex w-full items-center gap-2 text-[11.5px] font-semibold"
      >
        <KeyRound className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="flex-1 text-left">Development sign-ins</span>
        <span className="txt-faint">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open && (
        <div className="mt-2.5 flex flex-col gap-1.5">
          {ACCOUNTS.map(account => (
            <button
              key={account.email}
              type="button"
              onClick={() => onPick(account.email, PASSWORD)}
              className="hover:surface-2 rounded-md px-2 py-1.5 text-left transition-colors"
            >
              <span className="txt block text-[12px] font-semibold">
                {account.role}
                <span className="txt-faint font-normal"> — {account.hint}</span>
              </span>
              <span className="txt-faint block font-mono text-[11px]">{account.email}</span>
            </button>
          ))}
          <p className="txt-faint mt-1 px-2 text-[10.5px]">
            Password for all three: <span className="font-mono">{PASSWORD}</span>
          </p>
        </div>
      )}
    </div>
  );
}
