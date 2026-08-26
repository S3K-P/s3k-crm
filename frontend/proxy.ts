import { NextResponse, type NextRequest } from 'next/server';

import { API_BASE_URL, LOGIN_PATH, REFRESH_COOKIE_NAME } from '@/lib/api-config';

/**
 * Whether the API shares an origin with the frontend.
 *
 * The refresh cookie belongs to whichever host issued it. When the API runs on
 * a different origin, that cookie is simply not present on requests to the
 * Next.js server, so a cookie-based gate here would redirect every signed-in
 * user straight back to the login page. In that topology the gate stands down
 * and `RequireAuth` — which asks the API directly — does the work.
 *
 * A relative `API_BASE_URL` (the reverse-proxy deployment doc 11 assumes)
 * counts as same-origin.
 */
function apiSharesOrigin(request: NextRequest): boolean {
  if (!API_BASE_URL) return true;
  try {
    return new URL(API_BASE_URL).origin === request.nextUrl.origin;
  } catch {
    return true; // relative path, therefore same origin
  }
}

/**
 * Route protection for the authenticated CRM area.
 *
 * Named `proxy.ts` rather than `middleware.ts`: Next 16 deprecated the older
 * convention and warns about it on every boot. Behaviour is identical.
 *
 * This is a **cheap first gate**, not the security boundary. It checks only
 * that a refresh cookie is present — the middleware cannot validate a token
 * without a round trip, and doing one on every navigation would be wasteful.
 * Real enforcement is the backend's: every API call is authenticated and
 * authorized server-side, so a forged cookie gets an empty screen and 401s,
 * never data.
 *
 * The gate has no off switch. It previously stood down when
 * `NEXT_PUBLIC_API_BASE_URL` was unset, which meant a configuration slip
 * shipped an ungated application.
 */

/**
 * Paths under the `(crm)` route group that require a session.
 *
 * This list must cover every route in `app/(crm)`. A missing entry is not a
 * security hole — `RequireAuth` still gates the whole group client-side — but
 * it does mean an unauthenticated visitor renders the shell before being
 * bounced, which looks like a flash of the application.
 */
const PROTECTED_PREFIXES = [
  '/dashboard',
  '/leads',
  '/lead-sources',
  '/campaigns',
  '/meetings',
  '/accounts',
  '/contacts',
  '/opportunities',
  '/qualification',
  '/tasks',
  '/admin',
  '/ai',
  '/ai-settings',
];

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export default function proxy(request: NextRequest) {
  if (!apiSharesOrigin(request)) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  if (!isProtected(pathname)) return NextResponse.next();

  if (request.cookies.has(REFRESH_COOKIE_NAME)) return NextResponse.next();

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = LOGIN_PATH;
  // Preserve where they were heading so sign-in can return them there.
  loginUrl.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Everything except Next internals, the API proxy and static assets.
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\.).*)'],
};
