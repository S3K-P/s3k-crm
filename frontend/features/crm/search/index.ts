/**
 * Global CRM search — the client half of `GET /crm/search`.
 *
 * Mirrors `backend/app/products/crm/search/schemas.py`.
 *
 * **Nothing here filters results.** The backend returns only records the
 * caller may open, and it decides that inside the ranking query rather than
 * afterwards — so a client-side filter could only ever hide something the user
 * is entitled to see, while creating the impression that permission is a
 * front-end concern. `searched` says which entity types were actually
 * searched, which is the honest way to tell somebody they cannot search leads
 * rather than implying there are none.
 */

// `apiRequest` rather than the `api.get` shorthand: a search-as-you-type box
// must be able to abandon a request when the next keystroke arrives, and only
// the lower-level function forwards an `AbortSignal`. Widening `api.get` for
// one caller would have changed a signature every feature imports.
import { apiRequest } from '@/lib/api-client';

export type SearchEntityType = 'ACCOUNT' | 'CONTACT' | 'LEAD' | 'OPPORTUNITY';

export interface SearchHit {
  type: SearchEntityType;
  id: string;
  title: string;
  subtitle: string | null;
  /** Relevance, comparable across entity types. */
  score: number;
}

export interface SearchGroup {
  type: SearchEntityType;
  hits: SearchHit[];
}

export interface SearchResults {
  query: string;
  hits: SearchHit[];
  groups: SearchGroup[];
  /** Entity types the caller holds `VIEW` on. */
  searched: SearchEntityType[];
  truncated: boolean;
}

/** Matches `MIN_QUERY_LENGTH` in the search service. */
export const MIN_QUERY_LENGTH = 2;

/** Human labels and destinations, keyed by what the API returns. */
export const ENTITY_LABELS: Record<SearchEntityType, string> = {
  ACCOUNT: 'Accounts',
  CONTACT: 'Contacts',
  LEAD: 'Leads',
  OPPORTUNITY: 'Opportunities',
};

const ENTITY_ROUTES: Record<SearchEntityType, string> = {
  ACCOUNT: '/accounts',
  CONTACT: '/contacts',
  LEAD: '/leads',
  OPPORTUNITY: '/opportunities',
};

/** Where selecting a hit navigates to. */
export const hitHref = (hit: SearchHit) => `${ENTITY_ROUTES[hit.type]}/${hit.id}`;

export interface SearchParams {
  q: string;
  types?: SearchEntityType[];
  limit?: number;
}

export function searchCrm(
  { q, types, limit }: SearchParams,
  signal?: AbortSignal,
): Promise<SearchResults> {
  const query = new URLSearchParams({ q });
  if (limit !== undefined) query.set('limit', String(limit));
  // Repeated `types=` rather than a comma-joined value: FastAPI parses a
  // repeated query parameter into a list, and a comma-joined string would
  // arrive as one unparseable enum value.
  types?.forEach(type => query.append('types', type));

  return apiRequest<SearchResults>(`/crm/search?${query.toString()}`, {
    method: 'GET',
    signal,
  });
}
