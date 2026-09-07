'use client';

import { useSearchParams } from 'next/navigation';

/* ============================================================
   USE QUERY FILTER

   Seeds a list page's filter from the address bar, so a link
   can point at a *narrowed* list rather than at the top of an
   unfiltered one — `/tasks?status=PENDING` is the list the
   dashboard's "Tasks Due" tile counted, not merely the module
   that tile belongs to.

   The value is **validated against the enum the page accepts**
   before it is used. A hand-typed `?status=banana` would
   otherwise travel to the API and come back a 422, turning a
   mistyped URL into a broken screen; an unrecognised value is
   simply no filter at all.

   Read through `useSearchParams` rather than `window.location`
   for the reason spelled out in `opportunities/page.tsx`: on a
   client-side navigation the router renders the new route
   before the History API entry exists.

   This is a *seed*, not a binding. The filter is page state
   from the moment it is read, so changing the dropdown does not
   rewrite the URL and the URL does not fight the dropdown. Each
   arrival at the route mounts the page afresh, which is the
   only moment the query string has anything to say.
   ============================================================ */

export function useQueryFilter<T extends string>(
  param: string,
  allowed: readonly T[],
): T | '' {
  const value = useSearchParams().get(param);
  return value !== null && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : '';
}
