/**
 * Market Insights — types and API access.
 *
 * Mirrors `backend/app/products/crm/market_insights/schemas.py` and the AI
 * gateway's `schemas.py`. Every function here hits the real API; there is no
 * local fixture behind any of them, and none of the demonstration data still
 * sitting under `features/ai/insights` is imported.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';

/* ------------------------------------------------------------------
   Types
   ------------------------------------------------------------------ */

/**
 * Outcome of a research session.
 *
 * There is no in-flight value: the backend writes a row only once a turn has
 * finished, so a stored session is either usable or it failed. "Researching"
 * is a client-side state for the life of the request, not something the API
 * can report back.
 */
export type ResearchStatus = 'READY' | 'FAILED';
export type MessageRole = 'USER' | 'ASSISTANT';

/** A page the research actually retrieved. Never a fabricated citation. */
export interface ResearchSource {
  id: string;
  title: string;
  url: string;
  page_age: string | null;
  /** True when a sentence in the answer cited it, not merely read it. */
  cited: boolean;
  retrieved_at: string;
}

export interface ResearchMessage {
  id: string;
  sequence: number;
  role: MessageRole;
  /** Markdown. Section structure comes from the configured prompt. */
  content: string;
  truncated: boolean;
  search_count: number;
  author_id: string | null;
  created_at: string;
}

export interface ResearchSession extends RecordMeta {
  company_name: string;
  title: string;
  account_id: string | null;
  status: ResearchStatus;
  owner_id: string | null;
  model: string | null;
  prompt_version: number | null;
  used_crm_context: boolean;
  error_code: string | null;
  last_activity_at: string;
}

export interface ResearchSessionDetail extends ResearchSession {
  messages: ResearchMessage[];
  sources: ResearchSource[];
}

export interface AiStatus {
  configured: boolean;
  model: string | null;
}

export interface ResearchListParams extends ListParams {
  account_id?: string | null;
  status?: ResearchStatus | null;
}

/* ------------------------------------------------------------------
   Research
   ------------------------------------------------------------------ */

const BASE = '/crm/market-insights';

export const listResearch = (params?: ResearchListParams) =>
  api.get<Page<ResearchSession>>(`${BASE}${toQuery(params)}`);

export const getResearch = (id: string) => api.get<ResearchSessionDetail>(`${BASE}/${id}`);

/**
 * Start researching a company.
 *
 * `accountId` is omitted for an external company — the CRM does not need a
 * record before it can be researched.
 */
export const startResearch = (companyName: string, accountId?: string | null) =>
  api.post<ResearchSessionDetail>(BASE, {
    company_name: companyName,
    account_id: accountId ?? null,
  });

/** Ask a follow-up. The session keeps the company in context server-side. */
export const askFollowUp = (id: string, question: string) =>
  api.post<ResearchSessionDetail>(`${BASE}/${id}/messages`, { question });

export const renameResearch = (id: string, title: string) =>
  api.patch<ResearchSession>(`${BASE}/${id}`, { title });

/** Associate research with an account created through the normal CRM flow. */
export const linkResearchToAccount = (id: string, accountId: string) =>
  api.post<ResearchSession>(`${BASE}/${id}/account`, { account_id: accountId });

export const archiveResearch = (id: string) => api.delete<void>(`${BASE}/${id}`);

/* ------------------------------------------------------------------
   Gateway status and prompt configuration
   ------------------------------------------------------------------ */

export const getAiStatus = () => api.get<AiStatus>('/ai/status');

export interface PromptVersion {
  id: string;
  key: string;
  version: number;
  prompt: string;
  change_note: string | null;
  is_active: boolean;
  created_at: string;
  created_by_id: string | null;
}

export interface PromptSummary {
  id: string;
  version: number;
  change_note: string | null;
  is_active: boolean;
  created_at: string;
  created_by_id: string | null;
}

export interface PromptConfig {
  key: string;
  active: PromptVersion;
  history: PromptSummary[];
}

export const MARKET_INSIGHTS_PROMPT_KEY = 'market_insights';

/** Admin-only: the backend enforces `ai.ADMIN` on both of these. */
export const getPromptConfig = (key: string = MARKET_INSIGHTS_PROMPT_KEY) =>
  api.get<PromptConfig>(`/ai/prompts/${key}`);

export const publishPrompt = (
  prompt: string,
  changeNote: string | null,
  key: string = MARKET_INSIGHTS_PROMPT_KEY,
) => api.put<PromptConfig>(`/ai/prompts/${key}`, { prompt, change_note: changeNote });

/* ------------------------------------------------------------------
   Presentation helpers
   ------------------------------------------------------------------ */

/** Human-readable reason a research turn failed, keyed by backend error code. */
export const RESEARCH_ERROR_MESSAGES: Record<string, string> = {
  ai_not_configured:
    'AI is not connected. An administrator needs to configure an AI provider before research can run.',
  ai_temporarily_unavailable:
    'The AI service was busy and did not respond in time. Trying again usually works.',
  ai_provider_error: 'The AI provider could not complete this research.',
  ai_refused: 'The AI declined to research this subject.',
  ai_rate_limited: 'You have run a lot of research recently. Try again a little later.',
};

export function describeResearchError(code: string | null): string {
  if (!code) return 'This research did not complete.';
  return RESEARCH_ERROR_MESSAGES[code] ?? 'This research did not complete.';
}

/**
 * "Today · 4:20 PM", "Yesterday · 6:42 PM", "Aug 25 · 11:15 AM" — the format
 * the History list is specified in.
 */
export function formatHistoryTimestamp(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const time = date.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });

  const startOfDay = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const dayDelta = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);

  if (dayDelta === 0) return `Today · ${time}`;
  if (dayDelta === 1) return `Yesterday · ${time}`;

  const day = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  // Past years carry the year, so a stale session is not mistaken for a recent one.
  const year = date.getFullYear() === now.getFullYear() ? '' : `, ${date.getFullYear()}`;
  return `${day}${year} · ${time}`;
}

/** Hostname of a source URL, for the compact source chip. */
export function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}
