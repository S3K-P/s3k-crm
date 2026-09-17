/**
 * AI provider credentials — contracts and calls for the Providers screen.
 *
 * **No type here can carry an API key back from the server.** The only place a
 * key appears is the request body of {@link saveProviderCredential}, and it
 * travels one way: every response shape reports `masked_key` and a status. If
 * a field ever appears here that could hold plaintext, something has gone
 * wrong on the backend rather than in this file.
 */

import { api } from '@/lib/api-client';

const BASE = '/ai/providers';

/** What the last connectivity check concluded. */
export type CredentialStatus = 'UNVERIFIED' | 'CONNECTED' | 'INVALID';

export interface AiProvider {
  /** Machine identifier, e.g. `anthropic`. */
  provider: string;
  /** Human name for the card heading. */
  label: string;
  /** Whether this organization has stored a credential for it. */
  configured: boolean;
  /** `••••••••AB9f`, or `null` when nothing is stored. */
  masked_key: string | null;
  status: CredentialStatus | null;
  last_tested_at: string | null;
  /** Safe explanation of the last failure. Never the provider's raw text. */
  last_test_error: string | null;
  is_default: boolean;
  /** The model this provider runs on — each vendor names its own. */
  model: string;
}

export interface AiProvidersPayload {
  providers: AiProvider[];
  /**
   * Whether credentials can be *saved* at all on this deployment — false when
   * no encryption key is configured. Distinct from a provider merely being
   * unconfigured, and the screen says something different for each.
   */
  storage_available: boolean;
  /**
   * True when AI currently runs on the deployment-wide environment key rather
   * than anything this organization stored. Shown explicitly, because
   * "connected with nothing configured" otherwise reads as a bug.
   */
  using_environment_fallback: boolean;
}

export interface ProviderTestResult {
  ok: boolean;
  error: string | null;
  provider: AiProvider;
}

export const listProviders = () => api.get<AiProvidersPayload>(BASE);

/**
 * Store a credential. The server verifies it against the provider in the same
 * request, so the returned `ok` already reflects a real connectivity check
 * rather than merely a successful write.
 */
export const saveProviderCredential = (provider: string, apiKey: string) =>
  api.put<ProviderTestResult>(`${BASE}/${encodeURIComponent(provider)}`, {
    api_key: apiKey,
  });

/** Re-check a stored credential. Decrypts server-side, for one call. */
export const testProviderCredential = (provider: string) =>
  api.post<ProviderTestResult>(`${BASE}/${encodeURIComponent(provider)}/test`);

export const removeProviderCredential = (provider: string) =>
  api.delete<AiProvidersPayload>(`${BASE}/${encodeURIComponent(provider)}`);

export const makeProviderDefault = (provider: string) =>
  api.post<AiProvidersPayload>(`${BASE}/${encodeURIComponent(provider)}/default`);

/** Wording for a status pill, so every surface says the same thing. */
export const STATUS_LABEL: Record<CredentialStatus, string> = {
  CONNECTED: 'Connected',
  UNVERIFIED: 'Not tested',
  INVALID: 'Rejected',
};
