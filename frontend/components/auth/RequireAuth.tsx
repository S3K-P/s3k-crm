'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { useAuth } from '@/context/AuthContext';
import { LOGIN_PATH } from '@/lib/api-config';

/* ============================================================
   REQUIRE AUTH
   Client-side gate for the authenticated CRM area.

   `proxy.ts` gates on the server by looking for the refresh
   cookie, which is the fastest check but only works when the
   frontend and API share an origin — a cookie set by the API
   host is invisible to the Next.js server otherwise. This guard
   has no such constraint: it asks the API who the caller is, so
   protection holds whatever the deployment topology.

   Neither is the security boundary. The backend authenticates
   and authorizes every request; these two only decide what the
   browser bothers to render. Neither has an off switch: a
   misconfigured API URL leaves the user signed out, never
   signed in with everything unlocked.
   ============================================================ */

export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading || isAuthenticated) return;
    router.replace(`${LOGIN_PATH}?next=${encodeURIComponent(pathname)}`);
  }, [loading, isAuthenticated, router, pathname]);

  if (loading || !isAuthenticated) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: 'var(--bg)' }}
      >
        <div className="txt-muted flex items-center gap-2.5 text-[13px] font-medium">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          <span>{loading ? 'Restoring your session…' : 'Redirecting to sign in…'}</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
