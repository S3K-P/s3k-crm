'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, MessageSquare, Plus, Trash2 } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError } from '@/components/crm/shared/ListStates';
import { FormTextarea } from '@/components/crm/forms/FormField';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import { entityTimeline, type Activity } from '@/features/crm/activities';
import {
  archiveNote,
  createNote,
  listNotes,
  type Note,
} from '@/features/crm/notes';
import type { CrmEntityType } from '@/features/crm/tasks';

/* ============================================================
   RECORD PANELS

   The timeline and notes panels shared by every CRM detail page.
   Both read real, organization-scoped data:

   - the timeline from `GET /crm/activities/timeline`
   - notes from `GET /crm/notes`, already filtered server-side so
     another user's private notes never arrive here

   Both fail visibly rather than falling back to sample entries.
   ============================================================ */

function formatWhen(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ActivityTimelinePanel({
  entityType,
  entityId,
}: {
  entityType: CrmEntityType;
  entityId: string;
}) {
  const { can } = usePermissions();
  const mayView = can('activities', 'VIEW');

  const [items, setItems] = useState<Activity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await entityTimeline(entityType, entityId);
        if (!cancelled) {
          setItems(result);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(describeApiError(caught, 'Could not load the activity timeline.'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [entityType, entityId, mayView]);

  if (!mayView) return null;

  return (
    <div className="surface bd rounded-2xl border p-5">
      <SectionHeader title="Activity" />
      {error !== null ? (
        <p className="text-[12.5px] text-red-500">{error}</p>
      ) : items === null ? (
        <p className="txt-muted flex items-center gap-2 py-4 text-[12.5px]">
          <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" /> Loading…
        </p>
      ) : items.length === 0 ? (
        <p className="txt-faint py-4 text-center text-[12.5px]">
          Nothing recorded against this record yet.
        </p>
      ) : (
        <ul className="space-y-3 pt-1">
          {items.map((activity) => (
            <li key={activity.id} className="flex items-start gap-3">
              <span
                className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: 'var(--accent)' }}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="txt text-[13px] font-semibold">{activity.subject}</p>
                  <StatusBadge
                    label={humanize(activity.type)}
                    variant={statusVariant(activity.status)}
                  />
                </div>
                {activity.description && (
                  <p className="txt-muted mt-0.5 text-[12.5px]">{activity.description}</p>
                )}
                <p className="txt-faint mt-0.5 text-[11.5px]">
                  {formatWhen(
                    activity.completed_at ?? activity.due_date ?? activity.created_at,
                  )}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function NotesPanel({
  entityType,
  entityId,
}: {
  entityType: CrmEntityType;
  entityId: string;
}) {
  const { can } = usePermissions();
  const mayView = can('notes', 'VIEW');
  const mayCreate = can('notes', 'CREATE');
  const mayDelete = can('notes', 'DELETE');

  const [items, setItems] = useState<Note[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [token, setToken] = useState(0);
  const { pending, error: saveError, run } = useMutation();

  /** Bump to re-fetch after a create or delete. */
  const reload = useCallback(() => setToken((n) => n + 1), []);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;

    void (async () => {
      try {
        const result = await listNotes({
          related_entity_type: entityType,
          related_entity_id: entityId,
          page_size: 50,
          sort_by: 'created_at',
          sort_dir: 'desc',
        });
        if (!cancelled) {
          setItems(result.data);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load notes.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [entityType, entityId, mayView, token]);

  if (!mayView) return null;

  const handleAdd = async () => {
    if (!draft.trim()) return;
    const saved = await run(() =>
      createNote({
        content: draft.trim(),
        related_entity_type: entityType,
        related_entity_id: entityId,
      }),
    );
    if (saved === undefined) return;
    setDraft('');
    reload();
  };

  const handleDelete = async (note: Note) => {
    const done = await run(() => archiveNote(note.id));
    if (done !== undefined) reload();
  };

  return (
    <div className="surface bd rounded-2xl border p-5">
      <SectionHeader title="Notes" />

      {mayCreate && (
        <div className="space-y-2 pb-4">
          <FormTextarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={2}
            placeholder="Add a note…"
            aria-label="New note"
          />
          <div className="flex items-center justify-between gap-2">
            <FormError message={saveError} />
            <button
              type="button"
              onClick={() => void handleAdd()}
              disabled={pending || !draft.trim()}
              className="ml-auto flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending ? (
                <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              Add note
            </button>
          </div>
        </div>
      )}

      {error !== null ? (
        <p className="text-[12.5px] text-red-500">{error}</p>
      ) : items === null ? (
        <p className="txt-muted flex items-center gap-2 py-4 text-[12.5px]">
          <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" /> Loading…
        </p>
      ) : items.length === 0 ? (
        <p className="txt-faint py-4 text-center text-[12.5px]">
          <MessageSquare className="mx-auto mb-1.5 h-4 w-4" aria-hidden="true" />
          No notes yet.
        </p>
      ) : (
        <ul className="space-y-3">
          {items.map((note) => (
            <li key={note.id} className="bd rounded-xl border p-3">
              <p className="txt whitespace-pre-wrap text-[13px]">{note.content}</p>
              <div className="mt-1.5 flex items-center gap-2">
                <span className="txt-faint text-[11.5px]">
                  {formatWhen(note.created_at)}
                </span>
                <StatusBadge label={humanize(note.visibility)} variant="neutral" />
                {mayDelete && (
                  <button
                    type="button"
                    aria-label="Delete note"
                    onClick={() => void handleDelete(note)}
                    className="ml-auto text-red-500 transition hover:opacity-70"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
