'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Building2,
  Clock,
  Globe,
  Lock,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  TelescopeIcon,
} from 'lucide-react';
import { toast } from 'sonner';

import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import NotConfigured from '@/components/crm/shared/NotConfigured';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import CopyButton from '@/components/crm/ai/shared/CopyButton';
import CompanyPicker, {
  type CompanySelection,
} from '@/components/crm/ai/market-insights/CompanyPicker';
import ResearchProgress from '@/components/crm/ai/market-insights/ResearchProgress';
import ReportView from '@/components/crm/ai/market-insights/ReportView';
import SourcesPanel from '@/components/crm/ai/market-insights/SourcesPanel';
import FollowUpChat from '@/components/crm/ai/market-insights/FollowUpChat';
import DownloadReportMenu from '@/components/crm/ai/market-insights/DownloadReportMenu';
import HistoryList from '@/components/crm/ai/market-insights/HistoryList';
import AddToCrmDrawer from '@/components/crm/ai/market-insights/AddToCrmDrawer';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  archiveResearch,
  askFollowUp,
  formatHistoryTimestamp,
  getAiStatus,
  getResearch,
  listResearch,
  renameResearch,
  startResearch,
  type AiStatus,
  type ResearchSession,
  type ResearchSessionDetail,
} from '@/features/ai/market-insights';

/* ============================================================
   MARKET INSIGHTS

   AI company research inside the existing AI section.

   Two tabs, as specified: New Research and History. The page
   holds one "active session" — the thing being looked at —
   which is either freshly researched or restored from History.
   Restoring loads the stored conversation as written; it never
   re-runs the research or starts a fresh thread (§10).

   Three states gate the whole page, checked in order, because
   each answers a different question and they must not be
   conflated: is the user allowed here, is AI connected at all,
   and is there anything to show.
   ============================================================ */

type Tab = 'new' | 'history';

const HISTORY_PAGE_SIZE = 30;
const HISTORY_SEARCH_DEBOUNCE_MS = 250;

export default function MarketInsightsPage() {
  const { can, loading: authLoading, isAuthenticated, activeOrganizationId } = useAuth();

  const [tab, setTab] = useState<Tab>('new');

  /* --- Gateway status ------------------------------------------------ */
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  /* --- Active session ------------------------------------------------ */
  const [session, setSession] = useState<ResearchSessionDetail | null>(null);
  const [researching, setResearching] = useState(false);
  const [researchingName, setResearchingName] = useState('');
  const [researchError, setResearchError] = useState<string | null>(null);
  const [lastAttempt, setLastAttempt] = useState<CompanySelection | null>(null);

  /* --- Follow-up ----------------------------------------------------- */
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  /* --- History ------------------------------------------------------- */
  const [history, setHistory] = useState<ResearchSession[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historySearch, setHistorySearch] = useState('');
  const [historyReload, setHistoryReload] = useState(0);

  const [addToCrmOpen, setAddToCrmOpen] = useState(false);

  const canView = can('market_insights', 'VIEW');
  const canCreate = can('market_insights', 'CREATE');
  const canEdit = can('market_insights', 'EDIT');
  const canDelete = can('market_insights', 'DELETE');
  const canCreateAccounts = can('accounts', 'CREATE');

  /* ------------------------------------------------------------------
     Load the gateway status once the session is known.
     ------------------------------------------------------------------ */
  useEffect(() => {
    if (authLoading || !isAuthenticated || !canView) return;
    let cancelled = false;

    void (async () => {
      try {
        const status = await getAiStatus();
        if (!cancelled) {
          setAiStatus(status);
          setStatusError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setAiStatus(null);
          setStatusError(describeApiError(caught, 'Could not reach the AI service.'));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated, canView, activeOrganizationId]);

  /* ------------------------------------------------------------------
     History, debounced on the search term.
     ------------------------------------------------------------------ */
  useEffect(() => {
    if (authLoading || !isAuthenticated || !canView) return;
    let cancelled = false;

    const timer = setTimeout(() => {
      void (async () => {
        // Set here rather than in the effect body: the spinner belongs to the
        // request, and the request has not been made until the debounce fires.
        if (!cancelled) setHistoryLoading(true);
        try {
          const page = await listResearch({
            search: historySearch.trim() || null,
            page_size: HISTORY_PAGE_SIZE,
            sort_by: 'last_activity_at',
            sort_dir: 'desc',
          });
          if (!cancelled) {
            setHistory(page.data);
            setHistoryError(null);
          }
        } catch (caught) {
          if (!cancelled) {
            setHistory([]);
            setHistoryError(describeApiError(caught, 'Could not load research history.'));
          }
        } finally {
          if (!cancelled) setHistoryLoading(false);
        }
      })();
    }, HISTORY_SEARCH_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    authLoading,
    isAuthenticated,
    canView,
    historySearch,
    historyReload,
    activeOrganizationId,
  ]);

  const refreshHistory = useCallback(() => setHistoryReload((n) => n + 1), []);

  /* ------------------------------------------------------------------
     Actions
     ------------------------------------------------------------------ */

  const research = useCallback(
    async (selection: CompanySelection) => {
      setResearching(true);
      setResearchingName(selection.companyName);
      setResearchError(null);
      setAskError(null);
      setLastAttempt(selection);
      setSession(null);
      setTab('new');

      try {
        const detail = await startResearch(selection.companyName, selection.accountId);
        setSession(detail);
        refreshHistory();
      } catch (caught) {
        setResearchError(
          describeApiError(caught, 'The research could not be completed.'),
        );
        // A failed attempt is still stored server-side, so History stays truthful.
        refreshHistory();
      } finally {
        setResearching(false);
      }
    },
    [refreshHistory],
  );

  const ask = useCallback(
    async (question: string) => {
      if (session === null) return;
      setAsking(true);
      setAskError(null);
      try {
        const detail = await askFollowUp(session.id, question);
        setSession(detail);
        refreshHistory();
      } catch (caught) {
        setAskError(describeApiError(caught, 'That question could not be answered.'));
      } finally {
        setAsking(false);
      }
    },
    [session, refreshHistory],
  );

  const openSession = useCallback(async (summary: ResearchSession) => {
    setTab('new');
    setResearchError(null);
    setAskError(null);
    setResearching(true);
    setResearchingName(summary.company_name);
    try {
      // Loaded from the server rather than reconstructed, so the restored
      // conversation is exactly what was stored.
      const detail = await getResearch(summary.id);
      setSession(detail);
      if (detail.status === 'FAILED') {
        setResearchError(
          'This research did not complete. Start it again to try once more.',
        );
      }
    } catch (caught) {
      setSession(null);
      setResearchError(describeApiError(caught, 'That research could not be opened.'));
    } finally {
      setResearching(false);
    }
  }, []);

  const rename = useCallback(
    async (target: ResearchSession, title: string) => {
      try {
        const updated = await renameResearch(target.id, title);
        setHistory((current) =>
          current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
        );
        setSession((current) =>
          current && current.id === updated.id ? { ...current, title: updated.title } : current,
        );
        toast.success('Research renamed');
      } catch (caught) {
        toast.error(describeApiError(caught, 'The research could not be renamed.'));
      }
    },
    [],
  );

  const remove = useCallback(
    async (target: ResearchSession) => {
      try {
        await archiveResearch(target.id);
        setHistory((current) => current.filter((item) => item.id !== target.id));
        setSession((current) => (current && current.id === target.id ? null : current));
        toast.success('Research archived');
      } catch (caught) {
        toast.error(describeApiError(caught, 'The research could not be archived.'));
      }
    },
    [],
  );

  const startFresh = useCallback(() => {
    setSession(null);
    setResearchError(null);
    setAskError(null);
    setTab('new');
  }, []);

  /* ------------------------------------------------------------------
     Derived
     ------------------------------------------------------------------ */

  const report = useMemo(
    () => session?.messages.find((message) => message.role === 'ASSISTANT') ?? null,
    [session],
  );

  const aiUnavailable = aiStatus !== null && !aiStatus.configured;

  /* ------------------------------------------------------------------
     Gates
     ------------------------------------------------------------------ */

  if (!authLoading && isAuthenticated && !canView) {
    return (
      <PageFrame>
        <div className="surface bd rounded-2xl border p-6">
          <AiEmptyState
            icon={Lock}
            title="You do not have access to Market Insights"
            description="Ask an administrator to grant your role permission to view market research."
          />
        </div>
      </PageFrame>
    );
  }

  return (
    <PageFrame>
      {/* ── Tabs ── */}
      <div className="bd border-b">
        <div className="flex gap-6 px-1">
          {(
            [
              ['new', 'New Research', Sparkles],
              ['history', 'History', Clock],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              aria-current={tab === id ? 'page' : undefined}
              className={cn(
                'flex items-center gap-1.5 whitespace-nowrap border-b-2 py-3 text-[13.5px] font-semibold transition-colors',
                tab === id
                  ? 'border-[var(--accent)] text-[var(--accent)]'
                  : 'border-transparent text-[var(--muted)] hover:border-[var(--border)] hover:text-[var(--text)]',
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
              {id === 'history' && history.length > 0 && (
                <span className="txt-faint text-[11.5px] font-medium">({history.length})</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* The AI gateway not being connected is reported once, at the top,
          rather than as a failure on every action the user tries. */}
      {aiUnavailable && (
        <NotConfigured
          title="AI is not connected"
          description="Market Insights researches companies through an AI provider, and none is configured for this deployment. History and past reports are unaffected; new research cannot run until an administrator adds a provider credential."
          requires="AI provider credential (ADR-016)"
        />
      )}

      {statusError && !aiUnavailable && (
        <p className="txt-muted flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3.5 py-2.5 text-[12.5px]">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden="true" />
          {statusError}
        </p>
      )}

      {/* ── New Research ── */}
      {tab === 'new' && (
        <div className="space-y-4">
          {!session && !researching && (
            <div className="surface bd rounded-2xl border p-5 sm:p-6">
              <CompanyPicker
                onResearch={(selection) => void research(selection)}
                busy={researching}
                disabled={aiUnavailable || !canCreate}
              />

              {!canCreate && (
                <p className="txt-faint mt-3 text-[11.5px]">
                  Your role can read research but not start new research.
                </p>
              )}
            </div>
          )}

          {researching && (
            <ResearchProgress key={researchingName} companyName={researchingName} />
          )}

          {!researching && researchError && (
            <div className="surface bd rounded-2xl border p-6">
              <AiEmptyState
                icon={AlertTriangle}
                title="Research could not be completed"
                description={researchError}
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    {lastAttempt && canCreate && !aiUnavailable && (
                      <button
                        type="button"
                        onClick={() => void research(lastAttempt)}
                        className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
                        style={{ background: 'var(--accent)' }}
                      >
                        <RotateCcw className="h-4 w-4" aria-hidden="true" />
                        Try again
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={startFresh}
                      className="ctl txt-muted rounded-lg px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
                    >
                      Research a different company
                    </button>
                  </div>
                }
              />
            </div>
          )}

          {!researching && session && report && (
            <>
              <SessionHeader
                session={session}
                onNew={startFresh}
                onAddToCrm={() => setAddToCrmOpen(true)}
                canAddToCrm={canCreateAccounts}
                reportMarkdown={report.content}
              />

              {report.truncated && (
                <p className="txt-muted flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3.5 py-2.5 text-[12.5px]">
                  <AlertTriangle
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500"
                    aria-hidden="true"
                  />
                  This report was cut short before the model finished. Treat it as partial.
                </p>
              )}

              <div
                className={
                  session.sources.length > 0
                    ? 'grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]'
                    : 'space-y-4'
                }
              >
                <div className="min-w-0 space-y-4">
                  <ReportView markdown={report.content} companyName={session.company_name} />

                  <FollowUpChat
                    messages={session.messages}
                    onAsk={(question) => void ask(question)}
                    pending={asking}
                    error={askError}
                    disabled={aiUnavailable || !canEdit}
                  />
                </div>

                {session.sources.length > 0 && (
                  <div className="space-y-4 xl:sticky xl:top-4 xl:self-start">
                    <SourcesPanel sources={session.sources} />
                  </div>
                )}
              </div>
            </>
          )}

          {!researching && !session && !researchError && (
            <div className="surface bd rounded-2xl border p-6 sm:p-8">
              <div className="mx-auto max-w-2xl text-center">
                <div
                  className="mx-auto grid h-12 w-12 place-items-center rounded-2xl"
                  style={{ background: 'var(--accent-soft)' }}
                >
                  <TelescopeIcon className="h-6 w-6" style={{ color: 'var(--accent)' }} aria-hidden="true" />
                </div>
                <h2 className="font-display txt mt-3 text-[17px] font-extrabold">
                  Research any company
                </h2>
                <p className="txt-muted mx-auto mt-1.5 text-[13px] leading-relaxed">
                  Market Insights builds a current intelligence report from real sources — for
                  companies in your CRM and for ones you have never dealt with. What it covers
                  is set by the Market Insights prompt in AI Settings.
                </p>
              </div>

              <ul className="mx-auto mt-6 grid max-w-3xl gap-3 sm:grid-cols-2">
                {[
                  ['In your CRM', 'Research an existing account and the report uses its CRM context.', Building2],
                  ['External', 'Research any company by name — no CRM record needed first.', Globe],
                  ['Real sources', 'Every source shown was actually retrieved, with the date it was read.', Search],
                  ['Keeps context', 'Ask follow-up questions without naming the company again.', Sparkles],
                ].map(([title, description, Icon]) => {
                  const IconComponent = Icon as typeof Building2;
                  return (
                    <li key={title as string} className="surface-2 bd flex gap-2.5 rounded-xl border p-3.5">
                      <IconComponent
                        className="mt-0.5 h-4 w-4 shrink-0"
                        style={{ color: 'var(--accent)' }}
                        aria-hidden="true"
                      />
                      <span>
                        <span className="txt block text-[13px] font-semibold">{title as string}</span>
                        <span className="txt-muted mt-0.5 block text-[12px] leading-relaxed">
                          {description as string}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── History ── */}
      {tab === 'history' && (
        <HistoryList
          sessions={history}
          loading={historyLoading}
          error={historyError}
          search={historySearch}
          onSearchChange={setHistorySearch}
          onOpen={(item) => void openSession(item)}
          onRename={rename}
          onDelete={remove}
          canRename={canEdit}
          canDelete={canDelete}
          onRetryLoad={refreshHistory}
          activeId={session?.id ?? null}
        />
      )}

      {session && addToCrmOpen && (
        <AddToCrmDrawer
          open
          onClose={() => setAddToCrmOpen(false)}
          session={session}
          onLinked={(account) => {
            setSession((current) =>
              current ? { ...current, account_id: account.id } : current,
            );
            refreshHistory();
          }}
        />
      )}
    </PageFrame>
  );
}

/* ============================================================
   Page chrome — the header every state shares.
   ============================================================ */

function PageFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-5 p-6 lg:p-8">
      <header className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-600">
          <TelescopeIcon className="h-5 w-5 text-white" aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold leading-tight tracking-tight">
            Market Insights
          </h1>
          <p className="txt-muted mt-0.5 text-[13px] font-medium">
            AI company research with current, cited sources — for CRM accounts and companies you
            have never dealt with.
          </p>
        </div>
      </header>
      {children}
    </div>
  );
}

/* ============================================================
   The banner above a completed report: what was researched,
   under which prompt, and what can be done with it next.
   ============================================================ */

function SessionHeader({
  session,
  onNew,
  onAddToCrm,
  canAddToCrm,
  reportMarkdown,
}: {
  session: ResearchSessionDetail;
  onNew: () => void;
  onAddToCrm: () => void;
  canAddToCrm: boolean;
  reportMarkdown: string;
}) {
  const external = session.account_id === null;

  // Everything the exported document needs, in one object so the menu's
  // callbacks are not rebuilt on every keystroke elsewhere on the page.
  const exportDocument = useMemo(
    () => ({
      companyName: session.company_name,
      markdown: reportMarkdown,
      sources: session.sources,
      generatedAt: session.created_at,
      model: session.model,
      promptVersion: session.prompt_version,
      usedCrmContext: session.used_crm_context,
    }),
    [
      session.company_name,
      session.sources,
      session.created_at,
      session.model,
      session.prompt_version,
      session.used_crm_context,
      reportMarkdown,
    ],
  );

  return (
    <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5">
      <div className="flex min-w-0 items-start gap-3">
        <span
          className="surface-2 bd mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-[10px] border"
          aria-hidden="true"
        >
          {external ? (
            <Globe className="txt-faint h-4 w-4" />
          ) : (
            <Building2 className="h-4 w-4" style={{ color: 'var(--accent)' }} />
          )}
        </span>

        <div className="min-w-0">
          <h2 className="font-display txt truncate text-[17px] font-extrabold">
            {session.company_name}
          </h2>
          <p className="txt-muted mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px]">
            <span>{formatHistoryTimestamp(session.created_at)}</span>
            <span aria-hidden="true">·</span>
            <span>
              {session.used_crm_context
                ? 'CRM context used'
                : external
                  ? 'External company'
                  : 'CRM account'}
            </span>
            {session.prompt_version !== null && (
              <>
                <span aria-hidden="true">·</span>
                <span>prompt v{session.prompt_version}</span>
              </>
            )}
            {session.model && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono text-[11px]">{session.model}</span>
              </>
            )}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <CopyButton value={reportMarkdown} label="Report" showLabel />

        <DownloadReportMenu report={exportDocument} />

        {external && canAddToCrm && (
          <button
            type="button"
            onClick={onAddToCrm}
            className="ctl txt inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold transition hover:border-[var(--accent)] hover:opacity-90"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            Add to CRM
          </button>
        )}

        <button
          type="button"
          onClick={onNew}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90"
          style={{ background: 'var(--accent)' }}
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          New research
        </button>
      </div>
    </div>
  );
}
