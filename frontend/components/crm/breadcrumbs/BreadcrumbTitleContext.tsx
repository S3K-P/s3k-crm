'use client';

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react';
import { usePathname } from 'next/navigation';

/* ============================================================
   BREADCRUMB TITLE CONTEXT
   Lets a detail page hand its record's display name to the
   breadcrumb bar, so the last crumb reads "Acme Corp" instead
   of the raw id from the URL. The page already has the record,
   so this costs no extra request.
   ============================================================ */

/** A title is only ever valid for the path that published it. */
interface BreadcrumbEntry {
  path: string;
  title: string;
}

interface BreadcrumbTitleCtx {
  entry: BreadcrumbEntry | null;
  setEntry: Dispatch<SetStateAction<BreadcrumbEntry | null>>;
}

const BreadcrumbTitleContext = createContext<BreadcrumbTitleCtx | null>(null);

export function BreadcrumbTitleProvider({ children }: { children: ReactNode }) {
  const [entry, setEntry] = useState<BreadcrumbEntry | null>(null);

  return (
    <BreadcrumbTitleContext.Provider value={{ entry, setEntry }}>
      {children}
    </BreadcrumbTitleContext.Provider>
  );
}

/**
 * Read the title published for the current route.
 * Returns null when nothing was published, or when the only entry
 * belongs to a route we have already navigated away from.
 */
export function useBreadcrumbTitle(): string | null {
  const pathname = usePathname();
  const ctx = useContext(BreadcrumbTitleContext);
  if (!ctx?.entry) return null;
  return ctx.entry.path === pathname ? ctx.entry.title : null;
}

/**
 * Publish a record name for the current route's last crumb.
 * Call it unconditionally at the top of a detail page; pass a
 * falsy value while the record is still loading.
 */
export function useSetBreadcrumbTitle(title: string | null | undefined) {
  const pathname = usePathname();
  const setEntry = useContext(BreadcrumbTitleContext)?.setEntry;

  useEffect(() => {
    if (!setEntry) return; // Rendered outside the CRM shell — nothing to update.

    setEntry(title ? { path: pathname, title } : null);

    // Only retract our own entry, never one a newly mounted page just set.
    return () => setEntry(prev => (prev && prev.path === pathname ? null : prev));
  }, [setEntry, pathname, title]);
}
