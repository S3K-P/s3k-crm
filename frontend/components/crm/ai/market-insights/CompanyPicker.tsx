'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Building2, Globe, Loader2, Search, Sparkles, X } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { listAccounts, type Account } from '@/features/crm/accounts';

/* ============================================================
   COMPANY PICKER

   One input covering both halves of §3.

   Typing searches CRM accounts. Picking a result researches
   that account with its CRM context. Typing a name that matches
   nothing is not a dead end — it researches as an external
   company, with no requirement to create a CRM record first,
   which is the case the feature exists for.

   Matches are shown as suggestions rather than forced, so
   "Tata Chemicals" still researches externally when the CRM's
   "Tata Chemicals Europe" is not the company the user meant
   (§20, "multiple companies with similar names").
   ============================================================ */

const SEARCH_DEBOUNCE_MS = 250;
const MAX_SUGGESTIONS = 6;

export interface CompanySelection {
  companyName: string;
  accountId: string | null;
}

export default function CompanyPicker({
  onResearch,
  busy,
  disabled,
}: {
  onResearch: (selection: CompanySelection) => void;
  busy: boolean;
  disabled?: boolean;
}) {
  const { isAuthenticated, activeOrganizationId, can } = useAuth();
  const inputId = useId();

  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<Account | null>(null);
  const [matches, setMatches] = useState<Account[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);

  // The CRM half only applies to someone who may read accounts. Without the
  // permission the input still works — it just researches externally, which
  // is a working feature rather than a locked one.
  const canSearchAccounts = can('accounts', 'VIEW');

  /* --- CRM account lookup ------------------------------------------- */
  // `searchable` is the single condition for "this query is worth looking
  // up", used both to gate the request and to decide whether the stored
  // results still apply. Deriving it beats clearing `matches` in the effect:
  // one source of truth, and no synchronous setState during render.
  const term = query.trim();
  const searchable =
    canSearchAccounts && isAuthenticated && selected === null && term.length >= 2;

  useEffect(() => {
    if (!searchable) return;

    let cancelled = false;

    const timer = setTimeout(() => {
      void (async () => {
        // Set here rather than in the effect body: the spinner belongs to the
        // request, and no request exists until the debounce fires.
        if (!cancelled) setSearching(true);
        try {
          const page = await listAccounts({ search: term, page_size: MAX_SUGGESTIONS });
          if (!cancelled) {
            setMatches(page.data);
            setSearchError(null);
          }
        } catch (caught) {
          if (!cancelled) {
            setMatches([]);
            // Non-fatal: a failed lookup must not block external research.
            setSearchError(describeApiError(caught, 'Could not search CRM companies.'));
          }
        } finally {
          if (!cancelled) setSearching(false);
        }
      })();
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [term, searchable, activeOrganizationId]);

  /* --- Dismiss the suggestion list on an outside click ---------------- */
  useEffect(() => {
    if (!open) return;
    const handle = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  const choose = useCallback((account: Account) => {
    setSelected(account);
    setQuery(account.name);
    setMatches([]);
    setOpen(false);
  }, []);

  const clear = useCallback(() => {
    setSelected(null);
    setQuery('');
    setMatches([]);
    setOpen(false);
  }, []);

  const submit = useCallback(() => {
    const name = selected?.name ?? query.trim();
    if (name.length === 0 || busy) return;
    onResearch({ companyName: name, accountId: selected?.id ?? null });
  }, [selected, query, busy, onResearch]);

  const ready = (selected?.name ?? query.trim()).length > 0;
  // Stale results from a previous query are never shown: the list appears
  // only while the current query is still one worth searching for.
  const showSuggestions = open && searchable && matches.length > 0;

  return (
    <div ref={containerRef} className="relative">
      <label htmlFor={inputId} className="txt text-[13px] font-semibold">
        Company
      </label>
      <p className="txt-muted mt-0.5 text-[12.5px]">
        Search a company in your CRM, or type any company name to research it from scratch.
      </p>

      <div className="mt-2.5 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          {selected ? (
            <Building2
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
              style={{ color: 'var(--accent)' }}
              aria-hidden="true"
            />
          ) : (
            <Search
              className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
              aria-hidden="true"
            />
          )}

          <input
            id={inputId}
            type="text"
            value={query}
            disabled={disabled || busy}
            autoComplete="off"
            role="combobox"
            aria-expanded={showSuggestions}
            aria-controls={`${inputId}-suggestions`}
            placeholder="e.g. Apcotex Industries"
            onChange={(event) => {
              setQuery(event.target.value);
              setSelected(null);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                submit();
              }
              if (event.key === 'Escape') setOpen(false);
            }}
            className={cn(
              'ctl w-full py-2.5 pl-9 pr-9 text-[13px] outline-none transition-colors',
              'focus:border-[var(--accent)] disabled:opacity-60',
            )}
          />

          {(query.length > 0 || selected) && !busy && (
            <button
              type="button"
              onClick={clear}
              aria-label="Clear company"
              className="txt-faint absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 transition hover:opacity-70"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={submit}
          disabled={!ready || busy || disabled}
          className={cn(
            'flex items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white',
            'transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50',
          )}
          style={{ background: 'var(--accent)' }}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          )}
          {busy ? 'Researching…' : 'Research'}
        </button>
      </div>

      {/* Which of the two modes is about to run — stated before the click,
          so nobody is surprised by a report with no CRM context in it. */}
      <p className="txt-faint mt-2 flex items-center gap-1.5 text-[11.5px]">
        {selected ? (
          <>
            <Building2 className="h-3 w-3" aria-hidden="true" />
            Researching the CRM account <span className="txt font-semibold">{selected.name}</span>
            {' — your CRM data will be used as context.'}
          </>
        ) : ready ? (
          <>
            <Globe className="h-3 w-3" aria-hidden="true" />
            Not linked to a CRM company — this will be researched as an external company.
          </>
        ) : (
          <>
            {searchable && searching && (
              <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden="true" />
            )}
            {searchable && searching
              ? 'Searching your CRM…'
              : 'Any company can be researched, in the CRM or not.'}
          </>
        )}
      </p>

      {searchError && searchable && (
        <p className="txt-faint mt-1 text-[11.5px]">
          {searchError} You can still research this company externally.
        </p>
      )}

      {showSuggestions && (
        <ul
          id={`${inputId}-suggestions`}
          role="listbox"
          className="surface bd absolute z-20 mt-1.5 w-full overflow-hidden rounded-xl border shadow-lg"
        >
          <li className="txt-faint bd border-b px-3 py-1.5 text-[10.5px] font-bold uppercase tracking-wider">
            In your CRM
          </li>
          {matches.map((account) => (
            <li key={account.id}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => choose(account)}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition hover:bg-[var(--surface-2)]"
              >
                <Building2 className="txt-faint h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="txt block truncate text-[13px] font-semibold">
                    {account.name}
                  </span>
                  {(account.industry || account.website) && (
                    <span className="txt-faint block truncate text-[11.5px]">
                      {[account.industry, account.website].filter(Boolean).join(' · ')}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
          <li className="bd border-t">
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition hover:bg-[var(--surface-2)]"
            >
              <Globe className="txt-faint h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="txt-muted text-[12.5px]">
                None of these — research{' '}
                <span className="txt font-semibold">{query.trim()}</span> as an external company
              </span>
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}
