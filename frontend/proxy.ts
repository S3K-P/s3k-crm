import { NextResponse, type NextRequest } from 'next/server';

import { API_BASE_URL, AUTH_ENABLED, LOGIN_PATH, REFRESH_COOKIE_NAME } from '@/lib/api-config';

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
 * When no backend is configured (`NEXT_PUBLIC_API_BASE_URL` unset) the gate is
 * disabled entirely, so the existing demonstration pages keep working on a
 * fresh clone.
 */

/** Paths under the `(crm)` route group that require a session. */
const PROTECTED_PREFIXES = [
  '/dashboard',
  '/leads',
  '/lead-sources',
  '/partners',
  '/campaigns',
  '/meetings',
  '/accounts',
  '/contacts',
  '/opportunities',
  '/qualification',
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
  if (!AUTH_ENABLED) return NextResponse.next();
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
