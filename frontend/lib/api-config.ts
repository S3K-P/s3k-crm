/**
 * Backend connection settings.
 *
 * `NEXT_PUBLIC_API_BASE_URL` is the single switch that turns real
 * authentication on. When it is unset the app runs exactly as it did before
 * Phase 1 — every page renders its local demonstration data and no route is
 * gated — so a fresh clone still runs with no backend. Setting it makes the
 * frontend talk to the FastAPI service and enforces login on the CRM routes.
 */

export const API_BASE_URL: string = (process.env.NEXT_PUBLIC_API_BASE_URL ?? '').replace(
  /\/$/,
  '',
);

/** Whether a backend is configured, and therefore whether auth is enforced. */
export const AUTH_ENABLED: boolean = API_BASE_URL.length > 0;

/** Header the backend reads to select the active organization. */
export const ORGANIZATION_HEADER = 'X-Organization-Id';

/** Cookie the backend sets for the refresh token (httpOnly, not readable here). */
export const REFRESH_COOKIE_NAME = 's3k_refresh';

/** Where an unauthenticated visitor is sent. */
export const LOGIN_PATH = '/login';

/** Where a signed-in user lands. */
export const POST_LOGIN_PATH = '/dashboard';
