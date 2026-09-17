'use client';

import { useEffect, useState } from 'react';

import {
  getPublishedLayout,
  type LayoutEntityType,
  type LayoutType,
  type RecordLayoutDetail,
} from './index';

/**
 * The live layout for one entity type and screen, or `null` when none is
 * published.
 *
 * Same shape as `CustomFieldInputs.useEntitySchema`: the result is stamped
 * with the `entityType`/`layoutType` it answered and compared against the one
 * being rendered, so a late response for a previous request cannot repaint a
 * form with the wrong layout, and nothing calls `setState` synchronously
 * inside the effect.
 */
export function usePublishedLayout(
  entityType: LayoutEntityType | null,
  layoutType: LayoutType = 'DETAIL',
): {
  layout: RecordLayoutDetail | null;
  status: 'loading' | 'ready' | 'error';
} {
  const [result, setResult] = useState<{
    entityType: LayoutEntityType;
    layoutType: LayoutType;
    layout: RecordLayoutDetail | null;
    error: boolean;
  } | null>(null);

  useEffect(() => {
    if (entityType === null) return; // Nothing to fetch — handled below, at read time.
    let cancelled = false;

    void (async () => {
      try {
        const layout = await getPublishedLayout(entityType, layoutType);
        if (!cancelled) setResult({ entityType, layoutType, layout, error: false });
      } catch {
        // No published layout is not an error condition anywhere else in the
        // product; a form with no layout falls back to its own defaults, the
        // same way it behaved before Checkpoint 4 existed.
        if (!cancelled) setResult({ entityType, layoutType, layout: null, error: true });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [entityType, layoutType]);

  if (entityType === null) return { layout: null, status: 'ready' };
  const current =
    result?.entityType === entityType && result.layoutType === layoutType ? result : null;
  if (current === null) return { layout: null, status: 'loading' };
  return { layout: current.layout, status: current.error ? 'error' : 'ready' };
}
