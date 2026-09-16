'use client';

import { useCallback, useEffect, useState } from 'react';
import { BookmarkPlus, Loader2, Star, Trash2 } from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import type { ListParams } from '@/features/shared/types/api';
import {
  createView,
  deleteView,
  listViews,
  updateView,
  viewToParams,
  type SavedView,
  type ViewEntityType,
  type ViewFilters,
  type ViewVisibility,
} from '@/features/crm/views';

/* ============================================================
   SAVED VIEW PICKER

   The control that turns a list screen's current filters into a
   saved view, and a saved view back into filters.

   Two things it deliberately does not do:

   - **It does not fetch records.** Choosing a view hands its
     filters to the screen, which runs its own list call. So a
     shared view shows each viewer only what their permissions
     allow, and two colleagues opening one view legitimately see
     different rows.
   - **It does not decide who may edit.** `can_edit` comes from
     the server per request and is used to hide controls; the
     server refuses a write to somebody else's view whatever
     this component believed.

   The default view is applied once, on first load, and only when
   the screen has no filters of its own — a link carrying a
   filter must win over a saved preference, or a shared URL
   would open showing something else.
   ============================================================ */

interface SavedViewPickerProps {
  entityType: ViewEntityType;
  /** The screen's current filters, as it would send them to its list call. */
  current: ListParams;
  /** Apply a view's filters to the screen. */
  onApply: (params: ListParams) => void;
  /**
   * True when the screen's filters came from the URL rather than from the
   * user, which suppresses the default view.
   *
   * No list screen passes this today: the only URL parameters any of them
   * read (`?account_id=`) open the *create* drawer rather than filtering the
   * list, so there is nothing for a default view to override. It is part of
   * the contract rather than removed because the first screen to gain a real
   * URL filter needs it — without it, opening a shared link would apply
   * somebody's saved preference over the filter the link was sent for.
   */
  hasExplicitFilters?: boolean;
  /**
   * The screen's current visible-column keys (Checkpoint 4) — included when
   * saving a view and restored when one is chosen. Omit entirely on a screen
   * that has no column chooser; `SavedView.columns` still round-trips, this
   * just does not read or write it.
   */
  columns?: string[];
  onColumnsChange?: (columns: string[]) => void;
  className?: string;
}

export default function SavedViewPicker({
  entityType,
  current,
  onApply,
  hasExplicitFilters = false,
  columns,
  onColumnsChange,
  className,
}: SavedViewPickerProps) {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayUse = can('views', 'VIEW');
  const mayCreate = can('views', 'CREATE');

  const [views, setViews] = useState<SavedView[] | null>(null);
  const [selected, setSelected] = useState<string>('');
  const [saving, setSaving] = useState(false);
  // A small inline form rather than `window.prompt`: the native dialog blocks
  // the event loop, cannot be styled or themed, is unreachable to a screen
  // reader in the way the rest of the app is, and is invisible to an
  // end-to-end test without a dialog handler nobody remembers to add.
  const [naming, setNaming] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [shared, setShared] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // Applied at most once, and only if the screen was not already filtered.
  const [defaultApplied, setDefaultApplied] = useState(false);

  useEffect(() => {
    if (!mayUse) return;
    let cancelled = false;

    void (async () => {
      try {
        const loaded = await listViews(entityType);
        if (cancelled) return;
        setViews(loaded);

        const preferred = loaded.find((view) => view.is_default);
        if (preferred && !defaultApplied && !hasExplicitFilters) {
          setDefaultApplied(true);
          setSelected(preferred.id);
          onApply(viewToParams(preferred));
        }
      } catch (caught) {
        if (!cancelled) {
          setViews([]);
          notifyError(caught, describeApiError(caught, 'Saved views could not be loaded.'));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // `onApply` is recreated on every render by most callers and `current`
    // changes as the user types; neither changes which views exist.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mayUse, entityType, attempt]);

  if (!mayUse) return null;

  const choose = (id: string) => {
    setSelected(id);
    if (!id) {
      onApply({});
      return;
    }
    const view = views?.find((item) => item.id === id);
    if (view) {
      onApply(viewToParams(view));
      if (view.columns.length > 0) onColumnsChange?.(view.columns);
    }
  };

  const save = async () => {
    const name = draftName.trim();
    if (!name) return;

    setSaving(true);
    try {
      // `page` and `page_size` are stripped: a view is a filter set, and
      // reopening one should start at the beginning rather than on whatever
      // page its author happened to be on.
      const filters: ViewFilters = {};
      for (const [key, value] of Object.entries(current)) {
        if (key === 'page' || key === 'page_size') continue;
        if (key === 'sort_by' || key === 'sort_dir') continue;
        if (value === null || value === undefined || value === '') continue;
        filters[key] = value as ViewFilters[string];
      }

      const created = await createView({
        entity_type: entityType,
        name: name.trim(),
        filters,
        sort_by: (current.sort_by as string | null) ?? null,
        sort_dir: (current.sort_dir as 'asc' | 'desc' | undefined) ?? null,
        visibility: (shared ? 'ORGANIZATION' : 'PRIVATE') as ViewVisibility,
        columns: columns ?? [],
      });
      setSelected(created.id);
      setNaming(false);
      setDraftName('');
      setShared(false);
      notifySuccess('View saved', created.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The view could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  const makeDefault = async (view: SavedView) => {
    try {
      await updateView(view.id, { is_default: !view.is_default });
      notifySuccess(
        view.is_default ? 'No longer your default view' : 'Default view set',
        view.name,
      );
      reload();
    } catch (caught) {
      notifyError(caught, 'The default could not be changed.');
    }
  };

  const remove = async (view: SavedView) => {
    const ok = await confirm({
      title: `Delete "${view.name}"?`,
      description:
        'The saved filters are removed. No record is affected — a view holds none.',
      confirmLabel: 'Delete view',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await deleteView(view.id);
      if (selected === view.id) {
        setSelected('');
        onApply({});
      }
      notifySuccess('View deleted', view.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The view could not be deleted.');
    }
  };

  const active = views?.find((view) => view.id === selected) ?? null;

  return (
    <div className={className} data-testid="saved-view-picker">
      <div className="flex flex-wrap items-center gap-2">
        <FilterSelect
          aria-label="Saved view"
          value={selected}
          onChange={(event) => choose(event.target.value)}
          options={[
            { value: '', label: 'All records' },
            ...(views ?? []).map((view) => ({
              value: view.id,
              label: view.is_default ? `${view.name} ★` : view.name,
            })),
          ]}
        />

        {active && active.can_edit && (
          <>
            <button
              type="button"
              aria-label={
                active.is_default
                  ? `Stop opening ${active.name} by default`
                  : `Open ${active.name} by default`
              }
              onClick={() => void makeDefault(active)}
              className="ctl rounded-lg p-1.5 transition hover:opacity-70"
              title={active.is_default ? 'Your default view' : 'Make this your default'}
            >
              <Star
                className="h-3.5 w-3.5"
                style={active.is_default ? { color: 'var(--accent)' } : undefined}
              />
            </button>
            <button
              type="button"
              aria-label={`Delete ${active.name}`}
              onClick={() => void remove(active)}
              className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </>
        )}

        {mayCreate && !naming && (
          <button
            type="button"
            onClick={() => setNaming(true)}
            className="ctl bd flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
            title="Save the current filters as a view"
          >
            <BookmarkPlus className="h-3.5 w-3.5" />
            Save view
          </button>
        )}
      </div>

      {mayCreate && naming && (
        <form
          className="mt-2 flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <input
            autoFocus
            aria-label="Name this view"
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
            placeholder="Name this view…"
            maxLength={120}
            className="ctl max-w-[220px] px-3 py-1.5 text-[12px]"
          />
          <label className="flex items-center gap-1.5 text-[12px]">
            <input
              type="checkbox"
              checked={shared}
              onChange={(event) => setShared(event.target.checked)}
              className="h-3.5 w-3.5"
            />
            <span className="txt">Share with everyone</span>
          </label>
          <button
            type="submit"
            disabled={saving || !draftName.trim()}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {saving && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setNaming(false);
              setDraftName('');
            }}
            className="txt-faint text-[12px] underline transition hover:opacity-70"
          >
            Cancel
          </button>
        </form>
      )}
    </div>
  );
}
