/**
 * AI connection status — the one client for `GET /ai/status` and `POST /ai/health`.
 *
 * Mirrors `backend/app/platform/ai/schemas.py`. Nothing here decides whether
 * AI works: the backend says so, from its configuration and from what the
 * most recent real model call found. A key being present is reported as
 * `CONFIGURED`, never as connected — only a real round trip produces
 * `AVAILABLE`.
 */

import { api } from '@/lib/api-client';

/* ------------------------------------------------------------------
   Types
   ------------------------------------------------------------------ */

export type AiConnectionState =
  | 'NOT_CONFIGURED'
  | 'CONFIGURED'
  | 'AUTHENTICATION_ERROR'
  | 'PROVIDER_ERROR'
  | 'TIMEOUT'
  | 'AVAILABLE'
  | 'UNKNOWN_ERROR';

export type AiProvider = 'anthropic' | 'gemini';

/** Why `configured` is false. */
export type AiConfigurationIssue = 'missing_credential' | 'credential_for_other_provider';

/** What produced a verdict: an administrator's test, or a real feature call. */
export type AiCheckSource = 'health_check' | 'feature_call';

export interface AiStatus {
  configured: boolean;
  provider: AiProvider;
  /** The configured model id. Configuration, not a credential. */
  model: string | null;
  state: AiConnectionState;
  reason: AiConfigurationIssue | null;
  /** When a real call produced `state`; `null` when nothing has been verified. */
  checked_at: string | null;
  check_source: AiCheckSource | null;
  latency_ms: number | null;
  error_code: string | null;
}

export interface AiHealthCheck {
  provider: AiProvider;
  model: string;
  state: AiConnectionState;
  checked_at: string;
  latency_ms: number | null;
  error_code: string | null;
  /** The model the provider reported answering with. */
  responded_model: string | null;
}

/* ------------------------------------------------------------------
   API
   ------------------------------------------------------------------ */

/** Cheap: never calls a model. Every AI screen reads it on load. */
export const getAiStatus = () => api.get<AiStatus>('/ai/status');

/**
 * Admin-only (`ai.ADMIN`): one minimal *real* request to the configured model.
 * Spends a few tokens of provider quota, so it runs only when someone asks.
 */
export const runAiHealthCheck = () => api.post<AiHealthCheck>('/ai/health');

/* ------------------------------------------------------------------
   Presentation
   ------------------------------------------------------------------ */

/**
 * The four answers a screen has to tell apart. "AI is not connected" is
 * only ever the first; a screen whose feature is not built yet is `ready`.
 */
export type AiAvailability = 'not_configured' | 'auth_failed' | 'unavailable' | 'ready';

export function availabilityOf(state: AiConnectionState): AiAvailability {
  switch (state) {
    case 'NOT_CONFIGURED':
      return 'not_configured';
    case 'AUTHENTICATION_ERROR':
      return 'auth_failed';
    case 'PROVIDER_ERROR':
    case 'TIMEOUT':
    case 'UNKNOWN_ERROR':
      return 'unavailable';
    case 'CONFIGURED':
    case 'AVAILABLE':
      return 'ready';
  }
}

export const PROVIDER_LABELS: Record<AiProvider, string> = {
  anthropic: 'Anthropic Claude',
  gemini: 'Google Gemini',
};

/** The backend environment variable each provider reads its key from. */
export const PROVIDER_KEY_VARIABLE: Record<AiProvider, string> = {
  anthropic: 'ANTHROPIC_API_KEY',
  gemini: 'GEMINI_API_KEY',
};

/** The backend environment variable that picks each provider's model. */
export const PROVIDER_MODEL_VARIABLE: Record<AiProvider, string> = {
  anthropic: 'AI_MODEL',
  gemini: 'GEMINI_MODEL',
};

export const STATE_LABELS: Record<AiConnectionState, string> = {
  NOT_CONFIGURED: 'Not configured',
  CONFIGURED: 'Configured — not yet verified',
  AUTHENTICATION_ERROR: 'Credential rejected',
  PROVIDER_ERROR: 'Provider error',
  TIMEOUT: 'Timed out',
  AVAILABLE: 'Connected',
  UNKNOWN_ERROR: 'Unknown error',
};

const ERROR_CODE_MESSAGES: Record<string, string> = {
  credential_rejected: 'The provider rejected the configured API key.',
  timeout: 'The provider did not answer in time.',
  rate_limited: 'The provider is rate-limiting this key or its quota is used up.',
  model_not_found: 'The configured model is not available to this key.',
  provider_unavailable: 'The provider reported a server error.',
  connection_failed: 'The provider could not be reached.',
  empty_response: 'The provider answered without any content.',
  unexpected_error: 'An unexpected error occurred while calling the provider.',
  missing_credential: 'No API key is configured for the selected provider.',
  credential_for_other_provider:
    'The API key that is configured belongs to the provider AI_PROVIDER did not select.',
};

export function describeErrorCode(code: string | null): string {
  if (!code) return 'The provider did not complete the request.';
  const known = ERROR_CODE_MESSAGES[code];
  if (known) return known;
  const http = /^http_(\d{3})$/.exec(code);
  if (http) return `The provider answered with HTTP ${http[1]}.`;
  return 'The provider did not complete the request.';
}

/**
 * The administrator-facing reason AI is not configured. Names environment
 * variables — which are configuration — and never a value.
 */
export function describeNotConfigured(status: Pick<AiStatus, 'provider' | 'reason'>): string {
  const provider = PROVIDER_LABELS[status.provider];
  const keyVariable = PROVIDER_KEY_VARIABLE[status.provider];
  if (status.reason === 'credential_for_other_provider') {
    return `AI_PROVIDER selects ${provider} (${status.provider}), but ${keyVariable} is not set — the key that is set belongs to the other provider. Set AI_PROVIDER to the provider your key is for, or add ${keyVariable}, then restart the API.`;
  }
  return `AI_PROVIDER selects ${provider} (${status.provider}), and ${keyVariable} is not set. Add it to the backend environment and restart the API.`;
}

/** "just now", "12 min ago", "3 h ago", or a date for anything older. */
export function formatCheckedAt(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return '';
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return then.toLocaleString();
}
