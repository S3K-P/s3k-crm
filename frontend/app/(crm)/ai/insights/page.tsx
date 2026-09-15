'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertTriangle, BrainCircuit, Loader2, Search, Sparkles } from 'lucide-react';

import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import { useAiStatus } from '@/features/ai/useAiStatus';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  getInsightsDigest,
  runNlQuery,
  type InsightItem,
  type InsightsDigest,
  type NlQueryResponse,
} from '@/features/ai/ai-insights';

/* ============================================================
   AI INSIGHTS

   Two kinds of insight live here, and they are not the same thing:

   - The digest below (deals at risk, stale opportunities, neglected
     leads, quiet accounts, overdue tasks) is computed by SQL, not
     the model — every item is a fact a person could find by running
     the equivalent filtered list. It renders regardless of whether
     an AI provider is connected.
   - The question box calls the model to translate plain language
     into a report definition, then runs that through the same
     report engine a saved report uses. It needs AI connected.
   ============================================================ */

const ENTITY_ROUTE: Record<string, string> = {
  ACCOUNT: '/accounts',
  OPPORTUNITY: '/opportunities',
  LEAD: '/leads',
};

const SEVERITY_CLASS: Record<InsightItem['severity'], string> = {
  HIGH: 'border-rose-500/30 bg-rose-500/10 text-rose-600',
  MEDIUM: 'border-amber-500/30 bg-amber-500/10 text-amber-600',
  LOW: 'border-[var(--border)] bg-[var(--surface-2)] txt-muted',
};

function InsightRow({ item }: { item: InsightItem }) {
  const href = ENTITY_ROUTE[item.entity_type];
  const body = (
    <div className="flex items-start justify-between gap-3 py-2.5">
      <div className="min-w-0">
        <p className="txt truncate text-[13px] font-medium">{item.title}</p>
        {item.detail && <p className="txt-muted mt-0.5 text-[12px]">{item.detail}</p>}
      </div>
      <span
        className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${SEVERITY_CLASS[item.severity]}`}
      >
        {item.severity}
      </span>
    </div>
  );
  if (!href) return body;
  return (
    <Link href={`${href}/${item.entity_id}`} className="-mx-2 block rounded-lg px-2 hover:bg-[var(--surface-2)]">
      {body}
    </Link>
  );
}

function InsightSection({ title, items }: { title: string; items: InsightItem[] }) {
  return (
    <section className="surface bd rounded-2xl border p-5">
      <h2 className="txt font-display text-[14px] font-bold">
        {title} <span className="txt-faint font-normal">({items.length})</span>
      </h2>
      {items.length === 0 ? (
        <p className="txt-muted mt-2 text-[12.5px]">Nothing to flag right now.</p>
      ) : (
        <div className="bd mt-1 divide-y">
          {items.map((item) => (
            <InsightRow key={`${item.entity_type}-${item.entity_id}-${item.kind}`} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}

function QuestionBox() {
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<NlQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    if (!question.trim()) return;
    setAsking(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await runNlQuery(question.trim()));
    } catch (caught) {
      setError(describeApiError(caught, 'Could not answer that question.'));
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="surface bd rounded-2xl border p-5">
      <h2 className="txt font-display flex items-center gap-2 text-[14px] font-bold">
        <Search className="h-4 w-4" aria-hidden="true" /> Ask your pipeline a question
      </h2>
      <p className="txt-muted mt-1 text-[12.5px]">
        Plain language, translated into a report over your own CRM data — never a guess at the
        answer itself.
      </p>
      <div className="mt-3 flex gap-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && void ask()}
          placeholder="e.g. Which open deals are above ₹10,00,000?"
          className="ctl bd w-full rounded-lg border px-3 py-2 text-[13px]"
        />
        <button
          type="button"
          onClick={() => void ask()}
          disabled={asking || !question.trim()}
          className="btn-primary shrink-0 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {asking ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : 'Ask'}
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-[12.5px] text-rose-600">
          {error}
        </p>
      )}

      {answer && !answer.understood && (
        <p className="txt-muted mt-3 text-[12.5px]">
          {answer.clarification ?? "I couldn't turn that into a report — try naming the records and field you mean."}
        </p>
      )}

      {answer?.understood && answer.result && (
        <div className="bd mt-4 overflow-x-auto rounded-xl border">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="bd border-b" style={{ background: 'var(--surface-2)' }}>
                {answer.result.columns.map((column) => (
                  <th key={column.key} className="txt-muted px-3 py-2 text-left font-medium">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {answer.result.rows.map((row, index) => (
                <tr key={index} className="bd border-b last:border-b-0">
                  {answer.result!.columns.map((column) => (
                    <td key={column.key} className="txt px-3 py-2">
                      {String(row[column.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {answer.result.rows.length === 0 && (
            <p className="txt-muted p-3 text-[12.5px]">No matching records.</p>
          )}
        </div>
      )}
    </section>
  );
}

export default function AiInsightsPage() {
  const { status, error: statusError } = useAiStatus();
  const [digest, setDigest] = useState<InsightsDigest | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const loading = digest === null && loadError === null;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getInsightsDigest();
        if (!cancelled) setDigest(result);
      } catch (caught) {
        if (!cancelled) setLoadError(describeApiError(caught, 'Could not load insights.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-purple-600">
          <BrainCircuit className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">AI Insights</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            What in your pipeline needs attention, computed from your own CRM data.
          </p>
        </div>
      </div>

      <AiConnectionNotice
        status={status}
        error={statusError}
        hideWhenReady
        consequence="The digest below still works — it reads CRM data directly. Only the question box needs AI connected."
      />

      {loading && (
        <div role="status" aria-busy="true" className="txt-muted flex items-center gap-2 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> Loading insights…
        </div>
      )}

      {loadError && (
        <p role="alert" className="flex items-center gap-2 text-[13px] text-rose-600">
          <AlertTriangle className="h-4 w-4" aria-hidden="true" /> {loadError}
        </p>
      )}

      {digest && (
        <div className="grid gap-4 sm:grid-cols-2">
          <InsightSection title="Deals at risk" items={digest.deals_at_risk} />
          <InsightSection title="Stale opportunities" items={digest.stale_opportunities} />
          <InsightSection title="Neglected leads" items={digest.neglected_leads} />
          <InsightSection title="Accounts needing attention" items={digest.accounts_needing_attention} />
          <InsightSection title="Overdue tasks" items={digest.overdue_tasks} />
          <section className="surface bd flex flex-col justify-center rounded-2xl border p-5 text-center">
            <Sparkles className="txt-faint mx-auto h-5 w-5" aria-hidden="true" />
            <p className="txt-muted mt-2 text-[12px]">
              Open an account, deal or lead for an AI summary and next best action.
            </p>
          </section>
        </div>
      )}

      <QuestionBox />
    </div>
  );
}
