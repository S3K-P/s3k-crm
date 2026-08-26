'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowRight, Building2, Contact2, Loader2, Search, Target, TrendingUp, X,
  type LucideIcon,
} from 'lucide-react';

import { CRM_NAV_ITEMS } from '@/config/crm-navigation';
import {
  ENTITY_LABELS, MIN_QUERY_LENGTH, hitHref, searchCrm,
  type SearchEntityType, type SearchHit, type SearchResults,
} from '@/features/crm/search';

/* ============================================================
   COMMAND PALETTE (⌘K)

   Two things in one list, and the order is deliberate.

   *Records* come from `GET /crm/search` — real accounts, contacts,
   leads and opportunities, filtered by the backend to what this
   user may open. They are listed first because somebody who types
   a company name wants that company, not the Accounts page.

   *Pages* are matched locally against `CRM_NAV_ITEMS`, which is
   the same list the sidebar renders. Navigation is not data and
   does not need a round trip.

   The previous version of this modal searched only page names.
   That is what `P3-W20-FE-01` replaced: a palette that could not
   find a customer in a CRM.
   ============================================================ */

const ENTITY_ICONS: Record<SearchEntityType, LucideIcon> = {
  ACCOUNT: Building2,
  CONTACT: Contact2,
  LEAD: Target,
  OPPORTUNITY: TrendingUp,
};

/** Long enough that a fast typist sends one request, not eight. */
const DEBOUNCE_MS = 180;

type Row =
  | { kind: 'record'; key: string; label: string; sub: string | null; icon: LucideIcon; href: string }
  | { kind: 'page'; key: string; label: string; sub: null; icon: LucideIcon; href: string };

interface Section {
  heading: string;
  rows: Row[];
}

export default function CommandPalette({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const listRef = useRef<HTMLDivElement>(null);

  const trimmed = query.trim();

  /**
   * Results in state, but only while they still describe what is typed.
   *
   * The API echoes the query back precisely so a client can make this check.
   * It does two jobs at once: results for an abandoned query never render,
   * and shortening the box below the minimum hides them without an effect
   * having to clear state.
   */
  const current = results && results.query === trimmed ? results : null;

  /* --- Record search, debounced and cancellable ------------------------- */
  useEffect(() => {
    // Nothing to clear when the query is too short: what to *show* is derived
    // below from whether the results in state still describe what is typed.
    // Clearing here instead would mean calling setState from an effect on
    // every keystroke, and the answer is already computable during render.
    if (trimmed.length < MIN_QUERY_LENGTH) return;

    const controller = new AbortController();
    // Held across the debounce so a keystroke during the wait cancels the
    // timer, and one after the request has gone cancels the request. Without
    // the second, a slow reply for "acm" can land after a fast one for
    // "acme" and overwrite it.
    const timer = setTimeout(() => {
      setLoading(true);
      searchCrm({ q: trimmed }, controller.signal)
        .then(payload => {
          setResults(payload);
          setFailed(false);
          setActive(0);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setResults(null);
          setFailed(true);
          console.error('CRM search failed', error);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed]);

  /* --- Page matches, local -------------------------------------------- */
  const pageRows = useMemo<Row[]>(() => {
    const source = trimmed
      ? CRM_NAV_ITEMS.filter(item =>
          item.label.toLowerCase().includes(trimmed.toLowerCase()),
        )
      : CRM_NAV_ITEMS;
    return source.map(item => ({
      kind: 'page' as const,
      key: `page:${item.href}`,
      label: item.label,
      sub: null,
      icon: item.icon,
      href: item.href,
    }));
  }, [trimmed]);

  const sections = useMemo<Section[]>(() => {
    const built: Section[] = [];

    for (const group of current?.groups ?? []) {
      built.push({
        heading: ENTITY_LABELS[group.type],
        rows: group.hits.map((hit: SearchHit) => ({
          kind: 'record' as const,
          key: `${hit.type}:${hit.id}`,
          label: hit.title,
          sub: hit.subtitle,
          icon: ENTITY_ICONS[hit.type],
          href: hitHref(hit),
        })),
      });
    }

    if (pageRows.length) built.push({ heading: 'Go to', rows: pageRows });
    return built;
  }, [current, pageRows]);

  const flat = useMemo(() => sections.flatMap(section => section.rows), [sections]);

  /**
   * The highlighted row, clamped to what is actually on screen.
   *
   * The list shrinks as the query narrows — a page filter drops rows with no
   * API response to reset the cursor on — so the stored index can outrun it.
   * Clamped here during render rather than corrected in an effect: the safe
   * value is a function of what is rendered, so storing a bad one and fixing
   * it afterwards would be a wasted render for a number we already know.
   */
  const activeIndex = flat.length === 0 ? -1 : Math.min(active, flat.length - 1);

  const select = useCallback(
    (href: string) => {
      router.push(href);
      onClose();
    },
    [router, onClose],
  );

  /* --- Keyboard ------------------------------------------------------- */
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (!flat.length) return;
        setActive(current => {
          const next = event.key === 'ArrowDown' ? current + 1 : current - 1;
          // Wraps, because a list you can fall off the end of feels broken.
          return (next + flat.length) % flat.length;
        });
        return;
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        const row = flat[activeIndex];
        if (row) select(row.href);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose, flat, activeIndex, select]);

  // Keep the highlighted row on screen when arrowing past the fold.
  useEffect(() => {
    listRef.current
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const tooShort = trimmed.length > 0 && trimmed.length < MIN_QUERY_LENGTH;
  const emptyRecords =
    !loading && !failed && current !== null && current.hits.length === 0;

  let index = -1;

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search the CRM"
        className="surface bd fixed left-1/2 top-[12%] z-50 w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-2xl border shadow-[0_32px_80px_-20px_rgba(0,0,0,0.4)]"
      >
        <div className="bd flex items-center gap-3 border-b px-4 py-3.5">
          {loading
            ? <Loader2 className="h-5 w-5 shrink-0 animate-spin" style={{ color: 'var(--accent)' }} />
            : <Search className="h-5 w-5 shrink-0" style={{ color: 'var(--accent)' }} />}
          <input
            autoFocus
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search accounts, contacts, leads, deals…"
            aria-label="Search the CRM"
            className="txt flex-1 bg-transparent text-[15px] font-medium outline-none placeholder:opacity-50"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              aria-label="Clear search"
              className="txt-faint hover:opacity-70"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <kbd className="bd txt-faint hidden rounded-md border px-1.5 py-0.5 text-[10.5px] font-semibold sm:block">
            ESC
          </kbd>
        </div>

        <div ref={listRef} className="max-h-[420px] overflow-y-auto p-2">
          {failed && (
            <div className="txt-faint py-8 text-center text-sm">
              Search is unavailable right now. Page navigation below still works.
            </div>
          )}

          {tooShort && (
            <div className="txt-faint py-8 text-center text-sm">
              Keep typing — at least {MIN_QUERY_LENGTH} characters.
            </div>
          )}

          {emptyRecords && (
            <div className="txt-faint py-8 text-center text-sm">
              No records match &ldquo;{trimmed}&rdquo;.
            </div>
          )}

          {sections.map(section => (
            <div key={section.heading} className="mb-1">
              <div className="txt-faint px-3 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-wider">
                {section.heading}
              </div>
              {section.rows.map(row => {
                index += 1;
                const isActive = index === activeIndex;
                const position = index;
                return (
                  <button
                    key={row.key}
                    data-active={isActive}
                    onMouseEnter={() => setActive(position)}
                    onClick={() => select(row.href)}
                    className={`flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition-colors ${
                      isActive ? 'surface-2' : 'hover:surface-2'
                    }`}
                  >
                    <div className="surface-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px]">
                      <row.icon className="h-4 w-4" style={{ color: 'var(--accent)' }} />
                    </div>
                    <span className="min-w-0 flex-1">
                      <span className="txt block truncate text-[13.5px] font-medium">{row.label}</span>
                      {row.sub && (
                        <span className="txt-faint block truncate text-[11.5px]">{row.sub}</span>
                      )}
                    </span>
                    <ArrowRight className="txt-faint h-3.5 w-3.5 shrink-0" />
                  </button>
                );
              })}
            </div>
          ))}

          {current?.truncated && (
            <div className="txt-faint px-3 py-2 text-[11px]">
              More matches exist — try a longer search.
            </div>
          )}
        </div>

        <div className="bd txt-faint flex items-center gap-4 border-t px-4 py-2.5 text-[11px]">
          <span><kbd className="bd rounded border px-1 py-0.5 font-semibold">↑↓</kbd> navigate</span>
          <span><kbd className="bd rounded border px-1 py-0.5 font-semibold">↵</kbd> open</span>
          <span><kbd className="bd rounded border px-1 py-0.5 font-semibold">ESC</kbd> close</span>
        </div>
      </div>
    </>
  );
}
