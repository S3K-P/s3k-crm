'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { useAuth } from '@/context/AuthContext';

/* ============================================================
   REQUIRE ORGANIZATION

   Sits inside `RequireAuth`, and answers the question that only
   exists now that signup and tenant creation are two steps:
   *this person is signed in, but do they belong anywhere yet?*

   Someone who has created an S3K account and closed the tab
   mid-wizard comes back authenticated with no organization. The
   workspace has nothing to show them and the CRM would refuse
   every call, so they are returned to the step they stopped on
   rather than being shown an empty product or a wall of 403s.

   Not a security boundary. The backend refuses every
   tenant-scoped request without a verified membership; this only
   decides what the browser bothers to render.
   ============================================================ */

/** Where a signed-in user with no organization is sent to finish setting up. */
export const ONBOARDING_PATH = '/signup/organization';

export default function RequireOrganization({ children }: { children: React.ReactNode }) {
  const { loading, isAuthenticated, memberships } = useAuth();
  const router = useRouter();

  const needsOrganization = !loading && isAuthenticated && memberships.length === 0;

  useEffect(() => {
    if (needsOrganization) router.replace(ONBOARDING_PATH);
  }, [needsOrganization, router]);

  if (needsOrganization) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: 'var(--bg)' }}
      >
        <div className="txt-muted flex items-center gap-2.5 text-[13px] font-medium">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          <span>Taking you to set up your organization…</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
