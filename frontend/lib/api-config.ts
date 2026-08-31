/**
 * Backend connection settings.
 *
 * `NEXT_PUBLIC_API_BASE_URL` names the origin the API is served from. Leaving
 * it unset means **same-origin** — the reverse-proxy topology doc 11 assumes —
 * not "no backend".
 *
 * There is deliberately no switch here that turns authentication off. An
 * earlier revision derived an `AUTH_ENABLED` flag from this value, so a missing
 * or misspelled environment variable silently shipped an application with no
 * login gate and every permission granted. A configuration mistake must never
 * be able to widen access: if the API cannot be reached, the user sees an error
 * and stays signed out, which is the safe direction to fail.
 */

/** Origin of the API. Empty string means same-origin. */
export const API_BASE_URL: string = (process.env.NEXT_PUBLIC_API_BASE_URL ?? '')
  .trim()
  .replace(/\/$/, '');

/** Path prefix every API route sits behind. */
export const API_PREFIX = '/api/v1';

/** Header the backend reads to select the active organization. */
export const ORGANIZATION_HEADER = 'X-Organization-Id';

/** Cookie the backend sets for the refresh token (httpOnly, not readable here). */
export const REFRESH_COOKIE_NAME = 's3k_refresh';

/** Where an unauthenticated visitor is sent. */
export const LOGIN_PATH = '/login';

/**
 * Where a signed-in user lands.
 *
 * The S3K workspace, not the CRM dashboard: a user may hold several apps, and
 * dropping them straight into one of them is the thing that made the CRM feel
 * like the whole product. `/dashboard` still works and is still the CRM's own
 * landing page — it is simply no longer the platform's front door.
 */
export const POST_LOGIN_PATH = '/workspace';
