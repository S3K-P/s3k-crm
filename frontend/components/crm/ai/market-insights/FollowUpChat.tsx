'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowUp, Loader2, Sparkles, User } from 'lucide-react';

import { cn } from '@/lib/utils';
import CopyButton from '@/components/crm/ai/shared/CopyButton';
import MarkdownContent from '@/components/crm/ai/market-insights/MarkdownContent';
import { parseReport } from '@/features/ai/market-insights/markdown';
import type { ResearchMessage } from '@/features/ai/market-insights';

/* ============================================================
   FOLLOW-UP CHAT

   The conversation after the report (§6).

   The company stays in context server-side, so the user never
   restates it — "who are their biggest competitors?" resolves
   against the session, not against whatever was typed last.

   The opening report is not repeated here; it is rendered above
   by ReportView. This panel starts at the first follow-up.
   ============================================================ */

const MAX_QUESTION = 4_000;

/** Starters phrased the way the brief phrases them (§6). */
const SUGGESTIONS = [
  'Who are their biggest competitors?',
  'How should we approach this company?',
  'What changed about them recently?',
  'Give me a sales strategy.',
  'Summarise this in 5 points.',
] as const;

function MessageBubble({ message }: { message: ResearchMessage }) {
  const blocks = useMemo(
    () => parseReport(message.content).flatMap((section) =>
      section.title
        ? [{ kind: 'heading' as const, level: 3 as const, content: [{ kind: 'text' as const, text: section.title }] }, ...section.blocks]
        : section.blocks,
    ),
    [message.content],
  );

  if (message.role === 'USER') {
    return (
      <div className="flex justify-end">
        <div className="flex max-w-[85%] items-start gap-2.5">
          <div
            className="rounded-2xl rounded-tr-sm px-3.5 py-2.5 text-[13px] leading-relaxed text-white"
            style={{ background: 'var(--accent)' }}
          >
            {message.content}
          </div>
          <span
            className="surface-2 bd mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border"
            aria-hidden="true"
          >
            <User className="txt-faint h-3.5 w-3.5" />
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5">
      <span
        className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-600 to-indigo-600"
        aria-hidden="true"
      >
        <Sparkles className="h-3.5 w-3.5 text-white" />
      </span>
      <div className="surface-2 bd min-w-0 flex-1 rounded-2xl rounded-tl-sm border px-3.5 py-3">
        <MarkdownContent blocks={blocks} />

        <div className="mt-2.5 flex items-center justify-between gap-2">
          <span className="txt-faint text-[11px]">
            {message.search_count > 0
              ? `${message.search_count} web search${message.search_count === 1 ? '' : 'es'}`
              : 'Answered from this conversation'}
            {message.truncated && ' · answer was cut short'}
          </span>
          <CopyButton value={message.content} label="Answer" />
        </div>
      </div>
    </div>
  );
}

export default function FollowUpChat({
  messages,
  onAsk,
  pending,
  error,
  disabled,
}: {
  /** The full conversation. The opening request and report are skipped here. */
  messages: ResearchMessage[];
  onAsk: (question: string) => void;
  pending: boolean;
  error: string | null;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // The first two messages are the opening request and the report itself,
  // which ReportView already renders in full.
  const conversation = messages.slice(2);

  useEffect(() => {
    if (conversation.length > 0 || pending) {
      endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [conversation.length, pending]);

  const send = useCallback(
    (text: string) => {
      const question = text.trim();
      if (question.length === 0 || pending || disabled) return;
      onAsk(question);
      setDraft('');
    },
    [onAsk, pending, disabled],
  );

  return (
    <section className="surface bd overflow-hidden rounded-2xl border" aria-label="Follow-up">
      <header className="bd border-b px-4 py-3">
        <h3 className="txt font-display text-[14.5px] font-bold">Ask a follow-up</h3>
        <p className="txt-muted text-[12px]">
          The conversation keeps this company in context — no need to name it again.
        </p>
      </header>

      {(conversation.length > 0 || pending) && (
        <div className="max-h-[26rem] space-y-4 overflow-y-auto px-4 py-4">
          {conversation.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {pending && (
            <div className="flex items-start gap-2.5" aria-live="polite">
              <span
                className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-600 to-indigo-600"
                aria-hidden="true"
              >
                <Sparkles className="h-3.5 w-3.5 text-white" />
              </span>
              <div className="surface-2 bd flex items-center gap-2 rounded-2xl rounded-tl-sm border px-3.5 py-2.5">
                <Loader2
                  className="h-3.5 w-3.5 motion-safe:animate-spin"
                  style={{ color: 'var(--accent)' }}
                  aria-hidden="true"
                />
                <span className="txt-muted text-[12.5px]">Thinking…</span>
              </div>
            </div>
          )}

          <div ref={endRef} />
        </div>
      )}

      {conversation.length === 0 && !pending && (
        <div className="flex flex-wrap gap-1.5 px-4 pt-4">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={disabled}
              onClick={() => send(suggestion)}
              className="ctl txt-muted rounded-full px-3 py-1.5 text-[12px] font-medium transition hover:border-[var(--accent)] hover:opacity-90 disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {error && (
        <p className="mx-4 mt-3 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-[12.5px] text-red-500">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}

      <div className="bd mt-3 flex items-end gap-2 border-t px-4 py-3">
        <textarea
          ref={textareaRef}
          value={draft}
          rows={1}
          maxLength={MAX_QUESTION}
          disabled={pending || disabled}
          placeholder="Ask anything about this company…"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter is a newline — the convention every
            // chat surface in this application follows.
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              send(draft);
            }
          }}
          className={cn(
            'ctl max-h-32 min-h-[2.5rem] flex-1 resize-y px-3 py-2 text-[13px] outline-none',
            'transition-colors focus:border-[var(--accent)] disabled:opacity-60',
          )}
        />
        <button
          type="button"
          onClick={() => send(draft)}
          disabled={draft.trim().length === 0 || pending || disabled}
          aria-label="Send question"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-lg text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: 'var(--accent)' }}
        >
          {pending ? (
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          ) : (
            <ArrowUp className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </div>
    </section>
  );
}
