'use client';

import { useEffect, useState } from 'react';

import { getPublishedLayout, type LayoutEntityType, type RecordLayoutDetail } from './index';

/**
 * The live layout for one entity type, or `null` when none is published.
 *
 * Same shape as `CustomFieldInputs.useEntitySchema`: the result is stamped
 * with the `entityType` it answered and compared against the one being
 * rendered, so a late response for a previous entity type cannot repaint a
 * form with the wrong layout, and nothing calls `setState` synchronously
 * inside the effect.
 */
export function usePublishedLayout(entityType: LayoutEntityType | null): {
  layout: RecordLayoutDetail | null;
  status: 'loading' | 'ready' | 'error';
} {
  const [result, setResult] = useState<{
    entityType: LayoutEntityType;
    layout: RecordLayoutDetail | null;
    error: boolean;
  } | null>(null);

  useEffect(() => {
    if (entityType === null) return; // Nothing to fetch — handled below, at read time.
    let cancelled = false;

    void (async () => {
      try {
        const layout = await getPublishedLayout(entityType);
        if (!cancelled) setResult({ entityType, layout, error: false });
      } catch {
        // No published layout is not an error condition anywhere else in the
        // product; a form with no layout falls back to its own defaults, the
        // same way it behaved before Checkpoint 4 existed.
        if (!cancelled) setResult({ entityType, layout: null, error: true });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [entityType]);

  if (entityType === null) return { layout: null, status: 'ready' };
  const current = result?.entityType === entityType ? result : null;
  if (current === null) return { layout: null, status: 'loading' };
  return { layout: current.layout, status: current.error ? 'error' : 'ready' };
}
