'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  History,
  Loader2,
  Lock,
  MessageSquareCode,
  RotateCcw,
} from 'lucide-react';
import { toast } from 'sonner';

import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import NotConfigured from '@/components/crm/shared/NotConfigured';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  getPromptConfig,
  publishPrompt,
  type PromptConfig,
} from '@/features/ai/market-insights';

/* ============================================================
   PROMPT LIBRARY

   The Market Insights prompt, edited here and nowhere else
   (§11).

   Publishing appends a version rather than overwriting one, so
   research already performed keeps resolving to the wording
   that produced it (§12). That is a backend guarantee — this
   screen's job is to make it legible: the history list below
   shows every version, and the note under the editor says
   plainly that saving does not touch past research.

   Admin-only. The backend enforces `ai.ADMIN` on both the read
   and the write; hiding the form for anyone else is a courtesy,
   not the control.
   ============================================================ */

const MAX_PROMPT_LENGTH = 20_000;

export default function AIPromptsPage() {
  const { can, loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();
  const isAdmin = can('ai', 'ADMIN');

  const [config, setConfig] = useState<PromptConfig | null>(null);
  const [draft, setDraft] = useState('');
  const [changeNote, setChangeNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // `loading` starts false and is turned on by the fetch itself. Starting it
  // true would mean the not-allowed branch had to switch it off synchronously
  // inside the effect, which is the cascading-render pattern the lint rule
  // exists to catch.
  useEffect(() => {
    if (authLoading || !isAuthenticated || !isAdmin) return;
    let cancelled = false;

    void (async () => {
      setLoading(true);
      try {
        const loaded = await getPromptConfig();
        if (!cancelled) {
          setConfig(loaded);
          setDraft(loaded.active.prompt);
          setLoadError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setConfig(null);
          setLoadError(describeApiError(caught, 'The prompt could not be loaded.'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated, isAdmin, activeOrganizationId]);

  const save = useCallback(async () => {
    const prompt = draft.trim();
    if (prompt.length === 0) {
      setSaveError('The prompt cannot be empty.');
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      const updated = await publishPrompt(prompt, changeNote.trim() || null);
      setConfig(updated);
      setDraft(updated.active.prompt);
      setChangeNote('');
      toast.success(`Published version ${updated.active.version}`);
    } catch (caught) {
      setSaveError(describeApiError(caught, 'The prompt could not be published.'));
    } finally {
      setSaving(false);
    }
  }, [draft, changeNote]);

  const dirty = config !== null && draft.trim() !== config.active.prompt.trim();

  /* ---------------------------------------------------------------- */

  if (!authLoading && isAuthenticated && !isAdmin) {
    return (
      <Frame>
        <div className="surface bd rounded-2xl border p-6">
          <AiEmptyState
            icon={Lock}
            title="Administrators only"
            description="The Market Insights prompt controls what the AI researches for everyone in this organization, so only administrators can change it."
          />
        </div>
      </Frame>
    );
  }

  return (
    <Frame>
      {loading && (
        <div className="surface bd rounded-2xl border p-6" aria-busy="true">
          <div
            className="h-3.5 w-48 rounded motion-safe:animate-pulse"
            style={{ background: 'var(--border)' }}
          />
          <div
            className="mt-4 h-48 w-full rounded-xl motion-safe:animate-pulse"
            style={{ background: 'var(--border)' }}
          />
        </div>
      )}

      {!loading && !config && !loadError && (
        <div className="surface bd rounded-2xl border p-6" aria-busy="true">
          <div
            className="h-3.5 w-48 rounded motion-safe:animate-pulse"
            style={{ background: 'var(--border)' }}
          />
        </div>
      )}

      {!loading && loadError && (
        <NotConfigured
          title="The prompt could not be loaded"
          description={loadError}
          requires="AI gateway (ADR-016)"
        />
      )}

      {!loading && config && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          {/* ── Editor ── */}
          <section className="surface bd flex min-w-0 flex-col rounded-2xl border">
            <header className="bd flex items-center justify-between gap-3 border-b px-5 py-3.5">
              <div>
                <h2 className="txt font-display text-[15px] font-bold">
                  Market Insights prompt
                </h2>
                <p className="txt-muted text-[12px]">
                  Controls what company research covers and how it is presented.
                </p>
              </div>
              <span
                className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
              >
                v{config.active.version} active
              </span>
            </header>

            <div className="flex flex-1 flex-col gap-3 p-5">
              <label htmlFor="mi-prompt" className="sr-only">
                Market Insights prompt
              </label>
              <textarea
                id="mi-prompt"
                value={draft}
                maxLength={MAX_PROMPT_LENGTH}
                spellCheck
                onChange={(event) => {
                  setDraft(event.target.value);
                  setSaveError(null);
                }}
                className={cn(
                  'ctl min-h-[22rem] w-full flex-1 resize-y p-3.5 font-mono text-[12.5px] leading-relaxed',
                  'outline-none transition-colors focus:border-[var(--accent)]',
                )}
              />

              <div className="flex items-center justify-between gap-3">
                <p className="txt-faint text-[11.5px]">
                  {draft.length.toLocaleString()} / {MAX_PROMPT_LENGTH.toLocaleString()}{' '}
                  characters
                </p>
                {dirty && (
                  <p className="txt-muted text-[11.5px] font-medium">Unsaved changes</p>
                )}
              </div>

              <div>
                <label
                  htmlFor="mi-change-note"
                  className="txt text-[12.5px] font-semibold"
                >
                  What changed?
                </label>
                <input
                  id="mi-change-note"
                  value={changeNote}
                  maxLength={255}
                  placeholder="Optional — shown in the version history"
                  onChange={(event) => setChangeNote(event.target.value)}
                  className="ctl mt-1.5 w-full px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]"
                />
              </div>

              {saveError && (
                <p
                  className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-[12.5px] text-red-500"
                  role="alert"
                >
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  {saveError}
                </p>
              )}

              <p className="txt-muted bd flex items-start gap-2 rounded-xl border px-3.5 py-2.5 text-[12px] leading-relaxed">
                <History className="txt-faint mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                Publishing creates a new version. Research already completed stays exactly as it
                was written and keeps its own version — only new research uses this wording.
              </p>

              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  disabled={!dirty || saving}
                  onClick={() => {
                    setDraft(config.active.prompt);
                    setSaveError(null);
                  }}
                  className="ctl txt-muted inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-semibold transition hover:opacity-80 disabled:opacity-40"
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                  Revert
                </button>
                <button
                  type="button"
                  disabled={!dirty || saving}
                  onClick={() => void save()}
                  className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                  style={{ background: 'var(--accent)' }}
                >
                  {saving ? (
                    <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
                  ) : (
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  Publish version {config.active.version + 1}
                </button>
              </div>
            </div>
          </section>

          {/* ── Version history ── */}
          <aside className="surface bd h-fit rounded-2xl border">
            <header className="bd border-b px-4 py-3">
              <h2 className="txt font-display text-[14px] font-bold">Version history</h2>
              <p className="txt-muted text-[12px]">
                Every version stays readable. Nothing is overwritten.
              </p>
            </header>

            <ol className="divide-y divide-[var(--border)]">
              {config.history.map((version) => (
                <li key={version.id} className="flex items-start gap-2.5 px-4 py-3">
                  <span
                    className={cn(
                      'mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10.5px] font-bold',
                      version.is_active ? 'text-white' : 'surface-2 bd txt-muted border',
                    )}
                    style={version.is_active ? { background: 'var(--accent)' } : undefined}
                  >
                    {version.version}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="txt text-[12.5px] font-semibold">
                      Version {version.version}
                      {version.is_active && (
                        <span className="txt-faint ml-1.5 font-medium">· active</span>
                      )}
                    </p>
                    <p className="txt-faint text-[11.5px]">
                      {new Date(version.created_at).toLocaleString(undefined, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })}
                    </p>
                    {version.change_note && (
                      <p className="txt-muted mt-0.5 text-[11.5px] leading-snug">
                        {version.change_note}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      )}

      {/* Every other prompt in this section is still unbuilt, and saying so is
          better than implying a library that does not exist. */}
      <NotConfigured
        title="Other prompt templates"
        description="Market Insights is the only AI feature with a configurable prompt today. A general prompt library — reusable templates, variables and a playground — arrives with the rest of the AI gateway."
        requires="AI gateway (ADR-016, Phase 5)"
        compact
      />
    </Frame>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex h-full max-w-7xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
          <MessageSquareCode className="h-5 w-5 text-white" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">Prompt Library</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            The instructions driving your AI features, versioned so past output stays intact.
          </p>
        </div>
      </div>
      {children}
    </div>
  );
}
