/**
 * Notes — types and API access.
 *
 * Mirrors `backend/app/products/crm/notes/schemas.py`. Visibility is enforced
 * server-side inside the query: another user's private notes are never
 * returned, so nothing here needs to filter them out.
 */

import { api } from '@/lib/api-client';
import { toQuery, type ListParams, type Page, type RecordMeta } from '@/features/shared/types/api';
import type { CrmEntityType } from '@/features/crm/tasks';

export type NoteVisibility = 'PRIVATE' | 'TEAM' | 'ORGANIZATION';

export const NOTE_VISIBILITIES: NoteVisibility[] = ['PRIVATE', 'TEAM', 'ORGANIZATION'];

export interface Note extends RecordMeta {
  content: string;
  visibility: NoteVisibility;
  author_id: string | null;
  related_entity_type: CrmEntityType;
  related_entity_id: string;
}

export interface NoteInput {
  content: string;
  related_entity_type: CrmEntityType;
  related_entity_id: string;
  visibility?: NoteVisibility;
}

export interface NoteListParams extends ListParams {
  related_entity_type?: CrmEntityType | null;
  related_entity_id?: string | null;
}

export const listNotes = (params?: NoteListParams) =>
  api.get<Page<Note>>(`/crm/notes${toQuery(params)}`);

export const createNote = (body: NoteInput) => api.post<Note>('/crm/notes', body);

/** Authors only — the backend returns 403 for anyone else. */
export const updateNote = (
  id: string,
  body: { content?: string; visibility?: NoteVisibility },
) => api.patch<Note>(`/crm/notes/${id}`, body);

export const archiveNote = (id: string) => api.delete<void>(`/crm/notes/${id}`);
