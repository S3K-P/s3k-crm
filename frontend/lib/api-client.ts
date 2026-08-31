/**
 * Typed fetch wrapper for the S3K backend.
 *
 * Two things it is responsible for, and nothing else:
 *
 * 1. Attaching the in-memory access token and the active organization header.
 * 2. Transparently refreshing an expired access token once, then retrying.
 *
 * **The access token is never persisted.** It lives in a module variable for
 * the lifetime of the tab. The refresh token is an httpOnly cookie the browser
 * sends automatically and JavaScript cannot read — so an XSS flaw cannot steal
 * a long-lived credential. That is the whole point of the split, and it is why
 * nothing here touches `localStorage`.
 */

import { API_BASE_URL, API_PREFIX, ORGANIZATION_HEADER } from '@/lib/api-config';

/** Shape of the backend's structured error body. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody | null, fallback: string) {
    super(body?.error?.message ?? fallback);
    this.name = 'ApiError';
    this.status = status;
    this.code = body?.error?.code ?? 'unknown_error';
    this.details = body?.error?.details;
  }
}

/* ------------------------------------------------------------------
   In-memory session state
   ------------------------------------------------------------------ */

let accessToken: string | null = null;
let organizationId: string | null = null;
/** Set by the auth provider so a failed refresh can end the session. */
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setOrganizationId(id: string | null): void {
  organizationId = id;
}

export function getOrganizationId(): string | null {
  return organizationId;
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

/* ------------------------------------------------------------------
   Refresh
   ------------------------------------------------------------------ */

/** In-flight refresh, shared so concurrent 401s trigger only one rotation. */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  // Refresh tokens rotate on every use: two parallel refreshes would make the
  // second look like a replay and revoke the whole family. Share one promise.
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}${API_PREFIX}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!response.ok) return false;
      const body = (await response.json()) as { access_token: string };
      accessToken = body.access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

/* ------------------------------------------------------------------
   Request
   ------------------------------------------------------------------ */

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /**
   * A body to send as-is, for requests that are not JSON — a `FormData` file
   * upload being the only case today.
   *
   * When set, `Content-Type` is deliberately left unset: the browser has to
   * choose it so that the multipart boundary in the header matches the body it
   * generates. Setting it by hand produces a request the server cannot parse,
   * and the failure looks like a malformed file rather than a wrong header.
   */
  rawBody?: BodyInit;
  /** Skip the automatic refresh-and-retry (used by login/refresh themselves). */
  skipRefresh?: boolean;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = null;
  }
  return new ApiError(response.status, body, response.statusText || 'Request failed');
}

/**
 * Send a request with the session's credentials, refreshing once on a 401.
 *
 * Everything that touches the API goes through here — the JSON helpers below
 * and the CSV download alike. Keeping it in one function is the point: a
 * second copy of "attach the token, retry once, end the session if the refresh
 * fails" would be a second thing to get wrong, and the two would drift the
 * first time one of them was fixed.
 *
 * Returns the raw `Response`, still unread, so each caller decides how to
 * interpret a successful body. Errors are already normalised to `ApiError`.
 */
async function sendAuthenticated(
  path: string,
  options: RequestOptions & { accept?: string } = {},
): Promise<Response> {
  const { body, rawBody, skipRefresh, headers, accept, ...rest } = options;

  const send = async (): Promise<Response> => {
    const merged = new Headers(headers);
    // Left to the browser for a raw body — see `rawBody` above.
    if (rawBody === undefined) merged.set('Content-Type', 'application/json');
    if (accept) merged.set('Accept', accept);
    if (accessToken) merged.set('Authorization', `Bearer ${accessToken}`);
    if (organizationId) merged.set(ORGANIZATION_HEADER, organizationId);

    return fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
      ...rest,
      headers: merged,
      // Required for the refresh cookie to travel with the request.
      credentials: 'include',
      body: rawBody ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  };

  let response = await send();

  if (response.status === 401 && !skipRefresh) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await send();
    } else {
      accessToken = null;
      onSessionExpired?.();
      throw await parseError(response);
    }
  }

  if (!response.ok) throw await parseError(response);
  return response;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await sendAuthenticated(path, options);

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** A file the API returned, ready to be handed to the browser. */
export interface DownloadedFile {
  blob: Blob;
  /** Server-chosen filename, or `fallback` when the header is absent. */
  filename: string;
}

/**
 * Fetch a file rather than JSON, with the same authentication and retry.
 *
 * A plain `<a href>` cannot be used for these: the access token lives in
 * memory and never in a cookie, so a browser-initiated navigation would arrive
 * unauthenticated. The file therefore comes back through `fetch` and is handed
 * to the browser as an object URL by `saveFile`.
 */
export async function apiDownload(path: string, fallback: string): Promise<DownloadedFile> {
  const response = await sendAuthenticated(path, { method: 'GET', accept: 'text/csv' });
  const disposition = response.headers.get('content-disposition') ?? '';
  // Only the plain `filename="…"` form is produced by this API; a quoted value
  // is matched first so a name containing a semicolon cannot truncate it.
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);

  return { blob: await response.blob(), filename: match?.[1] ?? fallback };
}

export const api = {
  get: <T>(path: string) => apiRequest<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
};
