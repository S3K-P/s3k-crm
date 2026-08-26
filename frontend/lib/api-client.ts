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

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipRefresh, headers, ...rest } = options;

  const send = async (): Promise<Response> => {
    const merged = new Headers(headers);
    merged.set('Content-Type', 'application/json');
    if (accessToken) merged.set('Authorization', `Bearer ${accessToken}`);
    if (organizationId) merged.set(ORGANIZATION_HEADER, organizationId);

    return fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
      ...rest,
      headers: merged,
      // Required for the refresh cookie to travel with the request.
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
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
  if (response.status === 204) return undefined as T;

  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => apiRequest<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
};
