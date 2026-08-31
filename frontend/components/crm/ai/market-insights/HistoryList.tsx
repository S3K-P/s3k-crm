'use client';

import { useCallback, useState } from 'react';
import {
  AlertTriangle,
  Building2,
  Check,
  Globe,
  History,
  Loader2,
  Pencil,
  RotateCcw,
  SearchX,
  Trash2,
  X,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import SearchInput from '@/components/crm/forms/SearchInput';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import {
  describeResearchError,
  formatHistoryTimestamp,
  type ResearchSession,
} from '@/features/ai/market-insights';

/* ============================================================
   HISTORY LIST

   Past research, newest activity first (§9, §10).

   Rows render exactly the shape the brief specifies — company,
   title, relative timestamp — and carry the state that makes a
   row honest: whether it is linked to a CRM account, and
   whether the research actually completed. A failed attempt
   stays in the list with its reason rather than disappearing,
   so a user who hit a provider outage can find and retry it.
   ============================================================ */

export default function HistoryList({
  sessions,
  loading,
  error,
  search,
  onSearchChange,
  onOpen,
  onRename,
  onDelete,
  onRetryLoad,
  activeId,
  canRename = true,
  canDelete = true,
}: {
  sessions: ResearchSession[];
  loading: boolean;
  error: string | null;
  search: string;
  onSearchChange: (value: string) => void;
  onOpen: (session: ResearchSession) => void;
  onRename: (session: ResearchSession, title: string) => Promise<void>;
  onDelete: (session: ResearchSession) => Promise<void>;
  onRetryLoad: () => void;
  activeId?: string | null;
  /** Hide the actions the caller's role cannot perform.
   *
   *  Presentation only — the backend refuses either way. A button that is
   *  visible and then silently does nothing is worse than one that is absent. */
  canRename?: boolean;
  canDelete?: boolean;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const beginRename = useCallback((session: ResearchSession) => {
    setEditingId(session.id);
    setDraftTitle(session.title);
  }, []);

  const commitRename = useCallback(
    async (session: ResearchSession) => {
      const title = draftTitle.trim();
      setEditingId(null);
      if (title.length === 0 || title === session.title) return;
      setBusyId(session.id);
      try {
        await onRename(session, title);
      } finally {
        setBusyId(null);
      }
    },
    [draftTitle, onRename],
  );

  const remove = useCallback(
    async (session: ResearchSession) => {
      setBusyId(session.id);
      try {
        await onDelete(session);
      } finally {
        setBusyId(null);
      }
    },
    [onDelete],
  );

  return (
    <div className="space-y-3">
      <SearchInput
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="Search past research by company or title…"
        aria-label="Search research history"
      />

      {loading && (
        <div className="space-y-2" aria-busy="true">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="surface bd rounded-xl border p-3.5">
              <div
                className="h-3.5 w-40 rounded motion-safe:animate-pulse"
                style={{ background: 'var(--border)' }}
              />
              <div
                className="mt-2 h-2.5 w-28 rounded motion-safe:animate-pulse"
                style={{ background: 'var(--border)' }}
              />
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="surface bd rounded-2xl border p-4">
          <AiEmptyState
            icon={AlertTriangle}
            size="inline"
            title="History could not be loaded"
            description={error}
            action={
              <button
                type="button"
                onClick={onRetryLoad}
                className="ctl txt-muted inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Try again
              </button>
            }
          />
        </div>
      )}

      {!loading && !error && sessions.length === 0 && (
        <div className="surface bd rounded-2xl border p-4">
          <AiEmptyState
            icon={search.trim() ? SearchX : History}
            size="inline"
            title={search.trim() ? `No research matches “${search.trim()}”` : 'No research yet'}
            description={
              search.trim()
                ? 'Try a different company name, or clear the search.'
                : 'Research a company from the New Research tab and it will be saved here.'
            }
          />
        </div>
      )}

      {!loading && !error && sessions.length > 0 && (
        <ul className="space-y-2">
          {sessions.map((session) => {
            const editing = editingId === session.id;
            const busy = busyId === session.id;
            const failed = session.status === 'FAILED';

            return (
              <li
                key={session.id}
                className={cn(
                  'surface bd group rounded-xl border transition',
                  activeId === session.id && 'border-[var(--accent)]',
                )}
              >
                <div className="flex items-start gap-2 p-3.5">
                  <span
                    className="surface-2 bd mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border"
                    aria-hidden="true"
                  >
                    {session.account_id ? (
                      <Building2 className="h-4 w-4" style={{ color: 'var(--accent)' }} />
                    ) : (
                      <Globe className="txt-faint h-4 w-4" />
                    )}
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="txt truncate text-[13.5px] font-semibold">
                      {session.company_name}
                    </p>

                    {editing && canRename ? (
                      <div className="mt-1 flex items-center gap-1.5">
                        <input
                          autoFocus
                          value={draftTitle}
                          maxLength={255}
                          onChange={(event) => setDraftTitle(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') void commitRename(session);
                            if (event.key === 'Escape') setEditingId(null);
                          }}
                          className="ctl flex-1 px-2 py-1 text-[12px] outline-none focus:border-[var(--accent)]"
                          aria-label="Research title"
                        />
                        <button
                          type="button"
                          onClick={() => void commitRename(session)}
                          aria-label="Save title"
                          className="txt-muted rounded p-1 transition hover:opacity-70"
                        >
                          <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          aria-label="Cancel rename"
                          className="txt-muted rounded p-1 transition hover:opacity-70"
                        >
                          <X className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onOpen(session)}
                        className="txt-muted mt-0.5 block truncate text-left text-[12.5px] hover:underline"
                      >
                        {session.title}
                      </button>
                    )}

                    <p className="txt-faint mt-1 flex flex-wrap items-center gap-x-2 text-[11.5px]">
                      <span>{formatHistoryTimestamp(session.last_activity_at)}</span>
                      {session.used_crm_context && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>CRM context</span>
                        </>
                      )}
                      {session.prompt_version !== null && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>prompt v{session.prompt_version}</span>
                        </>
                      )}
                    </p>

                    {failed && (
                      <p className="mt-1.5 flex items-start gap-1.5 text-[11.5px] text-red-500">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                        {describeResearchError(session.error_code)}
                      </p>
                    )}
                  </div>

                  <div
                    className={cn(
                      'flex shrink-0 items-center gap-0.5 transition',
                      'opacity-0 focus-within:opacity-100 group-hover:opacity-100',
                    )}
                  >
                    {busy ? (
                      <Loader2
                        className="txt-faint m-1.5 h-3.5 w-3.5 motion-safe:animate-spin"
                        aria-hidden="true"
                      />
                    ) : (
                      <>
                        {canRename && (
                          <button
                            type="button"
                            onClick={() => beginRename(session)}
                            title="Rename"
                            aria-label={`Rename ${session.title}`}
                            className="txt-faint rounded p-1.5 transition hover:text-[var(--text)]"
                          >
                            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        )}
                        {canDelete && (
                          <button
                            type="button"
                            onClick={() => void remove(session)}
                            title="Archive"
                            aria-label={`Archive ${session.title}`}
                            className="txt-faint rounded p-1.5 transition hover:text-red-500"
                          >
                            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
