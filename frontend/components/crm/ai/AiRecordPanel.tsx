'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ArrowUpRight, Loader2, RefreshCw, Sparkles, Zap } from 'lucide-react';

import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import FeedbackButtons from '@/components/crm/ai/AiFeedbackButtons';
import {
  NbaNoRecommendation,
  NbaRecommendationBlock,
} from '@/components/crm/ai/next-best-action/NbaRecommendation';
import { recommendationOf } from '@/components/crm/ai/next-best-action/nba-view';
import { useAiStatus } from '@/features/ai/useAiStatus';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  applyMeetingActions,
  extractMeeting,
  generateAccountIntelligence,
  generateAccountSummary,
  generateLeadNextBestAction,
  generateLeadSummary,
  generateOpportunityNextBestAction,
  generateOpportunitySummary,
  getAccountIntelligence,
  getAccountSummary,
  getLeadNextBestAction,
  getLeadSummary,
  getOpportunityNextBestAction,
  getOpportunitySummary,
  type AccountIntelligenceContent,
  type AiGeneration,
  type MeetingAppliedItem,
  type MeetingExtractionContent,
  type RecordSummaryContent,
} from '@/features/ai/ai-insights';

/* ============================================================
   AI RECORD PANEL

   The Account/Opportunity/Lead-360 "AI" tab: a cached summary
   (and, for accounts, Account Intelligence; for deals and leads,
   Next Best Action), a Generate/Refresh action, and feedback.

   Every generation is real — permission-filtered CRM context sent
   through the same AI gateway Checkpoint 1 verified, validated
   against a Pydantic schema before it ever reaches this component
   (`ai_insights/structured.py`). Nothing here renders a fixture.
   ============================================================ */

type EntityKind = 'ACCOUNT' | 'OPPORTUNITY' | 'LEAD';

const SUMMARY_OPS: Record<
  EntityKind,
  { get: (id: string) => Promise<AiGeneration | null>; generate: (id: string) => Promise<AiGeneration> }
> = {
  ACCOUNT: { get: getAccountSummary, generate: generateAccountSummary },
  OPPORTUNITY: { get: getOpportunitySummary, generate: generateOpportunitySummary },
  LEAD: { get: getLeadSummary, generate: generateLeadSummary },
};

/**
 * A cached generation for one entity, keyed so a stale in-flight fetch from a
 * previous `entityId` never overwrites the current one — the same guarded
 * shape `useRecord` uses, so no `setState` runs synchronously in the effect
 * body (only after the fetch settles).
 */
function useCachedGeneration(
  entityId: string,
  fetcher: (id: string) => Promise<AiGeneration | null>,
): [AiGeneration | null | undefined, (generation: AiGeneration) => void] {
  const [state, setState] = useState<{ id: string; generation: AiGeneration | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const generation = await fetcher(entityId);
        if (!cancelled) setState({ id: entityId, generation });
      } catch {
        if (!cancelled) setState({ id: entityId, generation: null });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [entityId, fetcher]);

  const generation = state && state.id === entityId ? state.generation : undefined;
  const setGeneration = (next: AiGeneration) => setState({ id: entityId, generation: next });
  return [generation, setGeneration];
}

const NBA_OPS: Partial<
  Record<
    EntityKind,
    { get: (id: string) => Promise<AiGeneration | null>; generate: (id: string) => Promise<AiGeneration> }
  >
> = {
  OPPORTUNITY: { get: getOpportunityNextBestAction, generate: generateOpportunityNextBestAction },
  LEAD: { get: getLeadNextBestAction, generate: generateLeadNextBestAction },
};

function GenerateButton({
  hasResult,
  generating,
  onClick,
}: {
  hasResult: boolean;
  generating: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={generating}
      className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {generating ? (
        <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
      ) : hasResult ? (
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {generating ? 'Generating…' : hasResult ? 'Refresh' : 'Generate'}
    </button>
  );
}

function SummaryCard({ entityType, entityId }: { entityType: EntityKind; entityId: string }) {
  const ops = SUMMARY_OPS[entityType];
  const [generation, setGeneration] = useCachedGeneration(entityId, ops.get);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      setGeneration(await ops.generate(entityId));
    } catch (caught) {
      setError(describeApiError(caught, 'Could not generate a summary.'));
    } finally {
      setGenerating(false);
    }
  }

  const content = generation?.content as RecordSummaryContent | undefined;

  return (
    <section className="surface bd rounded-2xl border p-5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="txt font-display text-[13.5px] font-bold">AI summary</h3>
        <div className="flex items-center gap-2">
          {generation && <FeedbackButtons generation={generation} />}
          <GenerateButton hasResult={!!generation} generating={generating} onClick={() => void generate()} />
        </div>
      </div>
      {error && <p className="mt-2 text-[12px] text-rose-600">{error}</p>}
      {generation === undefined && (
        <p className="txt-muted mt-2 text-[12.5px]">Loading…</p>
      )}
      {generation === null && !error && (
        <p className="txt-muted mt-2 text-[12.5px]">No summary yet — press Generate.</p>
      )}
      {content && <p className="txt mt-2 text-[13px] leading-relaxed">{content.summary}</p>}
    </section>
  );
}

function IntelligenceCard({ entityId }: { entityId: string }) {
  const [generation, setGeneration] = useCachedGeneration(entityId, getAccountIntelligence);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      setGeneration(await generateAccountIntelligence(entityId));
    } catch (caught) {
      setError(describeApiError(caught, 'Could not generate account intelligence.'));
    } finally {
      setGenerating(false);
    }
  }

  const content = generation?.content as AccountIntelligenceContent | undefined;

  return (
    <section className="surface bd rounded-2xl border p-5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="txt font-display text-[13.5px] font-bold">Account intelligence</h3>
        <div className="flex items-center gap-2">
          {generation && <FeedbackButtons generation={generation} />}
          <GenerateButton hasResult={!!generation} generating={generating} onClick={() => void generate()} />
        </div>
      </div>
      {error && <p className="mt-2 text-[12px] text-rose-600">{error}</p>}
      {generation === undefined && <p className="txt-muted mt-2 text-[12.5px]">Loading…</p>}
      {generation === null && !error && (
        <p className="txt-muted mt-2 text-[12.5px]">No report yet — press Generate.</p>
      )}
      {content && (
        <div className="mt-2 space-y-3 text-[13px]">
          <p className="txt leading-relaxed">{content.summary}</p>
          <div className="flex items-center gap-2">
            <span className="txt-muted text-[12px] font-semibold">Relationship health:</span>
            <span className="txt">{content.relationship_health.status}</span>
          </div>
          <p className="txt-muted text-[12px]">{content.relationship_health.rationale}</p>
          {content.risks.length > 0 && (
            <div>
              <p className="txt-muted text-[12px] font-semibold uppercase">Risks</p>
              <ul className="txt mt-1 list-disc space-y-0.5 pl-4 text-[12.5px]">
                {content.risks.map((risk) => (
                  <li key={risk}>{risk}</li>
                ))}
              </ul>
            </div>
          )}
          {content.opportunities.length > 0 && (
            <div>
              <p className="txt-muted text-[12px] font-semibold uppercase">Opportunities</p>
              <ul className="txt mt-1 list-disc space-y-0.5 pl-4 text-[12.5px]">
                {content.opportunities.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {content.recommended_actions.length > 0 && (
            <div>
              <p className="txt-muted text-[12px] font-semibold uppercase">Recommended actions</p>
              <ul className="txt mt-1 list-disc space-y-0.5 pl-4 text-[12.5px]">
                {content.recommended_actions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

async function noNextBestAction(): Promise<AiGeneration | null> {
  return null;
}

function NextBestActionCard({ entityType, entityId }: { entityType: EntityKind; entityId: string }) {
  const ops = NBA_OPS[entityType];
  const [generation, setGeneration] = useCachedGeneration(entityId, ops?.get ?? noNextBestAction);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!ops) return null;

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      setGeneration(await ops!.generate(entityId));
    } catch (caught) {
      setError(describeApiError(caught, 'Could not generate a recommendation.'));
    } finally {
      setGenerating(false);
    }
  }

  const recommendation = recommendationOf(generation);

  /* Same recommendation block as the global Next Best Action queue, so a
     rep moving between the queue and the record sees one thing, not two. */
  return (
    <section className="surface bd rounded-2xl border p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="txt font-display flex items-center gap-2 text-[13.5px] font-bold">
          <Zap className="h-4 w-4" style={{ color: 'var(--accent)' }} aria-hidden="true" />
          Next best action
        </h3>
        <div className="flex items-center gap-2">
          <Link
            href="/ai/next-best-action"
            className="txt-muted inline-flex items-center gap-1 text-[12px] font-semibold transition hover:text-[var(--text)]"
          >
            Full queue <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
          <GenerateButton hasResult={!!recommendation} generating={generating} onClick={() => void generate()} />
        </div>
      </div>
      {error && <p className="mt-2 text-[12px] text-rose-600">{error}</p>}
      {generation === undefined && <p className="txt-muted mt-2 text-[12.5px]">Loading…</p>}
      <div className="mt-3">
        {recommendation ? (
          <NbaRecommendationBlock
            recommendation={recommendation}
            headerAside={<FeedbackButtons key={recommendation.generation.id} generation={recommendation.generation} />}
          />
        ) : (
          generation !== undefined &&
          !error && <NbaNoRecommendation note="Press Generate to ask for one from this record’s CRM context." />
        )}
      </div>
    </section>
  );
}

function MeetingExtractionCard({ entityType, entityId }: { entityType: EntityKind; entityId: string }) {
  const [notes, setNotes] = useState('');
  const [extraction, setExtraction] = useState<{
    generationId: string;
    content: MeetingExtractionContent;
  } | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [results, setResults] = useState<MeetingAppliedItem[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function extract() {
    if (!notes.trim()) return;
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const key = entityType === 'ACCOUNT' ? 'account_id' : 'opportunity_id';
      const generation = await extractMeeting({ text: notes.trim(), [key]: entityId });
      setExtraction({
        generationId: generation.id,
        content: generation.content as unknown as MeetingExtractionContent,
      });
      setSelected(new Set());
    } catch (caught) {
      setError(describeApiError(caught, 'Could not extract this meeting.'));
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!extraction || selected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      const { results: outcomes } = await applyMeetingActions(
        extraction.generationId,
        Array.from(selected),
      );
      setResults(outcomes);
    } catch (caught) {
      setError(describeApiError(caught, 'Could not apply the selected items.'));
    } finally {
      setBusy(false);
    }
  }

  function toggle(index: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <section className="surface bd rounded-2xl border p-5">
      <h3 className="txt font-display text-[13.5px] font-bold">Meeting notes → CRM</h3>
      <p className="txt-muted mt-1 text-[12px]">
        Paste meeting notes or a transcript. Nothing is written to this record until you review and
        apply the items below.
      </p>
      <textarea
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        rows={3}
        placeholder="Paste meeting notes or a transcript…"
        className="ctl bd mt-2 w-full rounded-lg border px-3 py-2 text-[13px]"
      />
      <button
        type="button"
        onClick={() => void extract()}
        disabled={busy || !notes.trim()}
        className="ctl bd mt-2 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy && !extraction ? (
          <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
        ) : (
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        Extract
      </button>
      {error && <p className="mt-2 text-[12px] text-rose-600">{error}</p>}

      {extraction && (
        <div className="mt-3 space-y-3 text-[13px]">
          <p className="txt leading-relaxed">{extraction.content.summary}</p>
          {extraction.content.follow_up_actions.length > 0 && (
            <div className="bd space-y-2 rounded-lg border p-3">
              <p className="txt-muted text-[11.5px] font-semibold uppercase">
                Follow-up items — select which to create
              </p>
              {extraction.content.follow_up_actions.map((item, index) => {
                const outcome = results?.[index]?.outcome;
                return (
                  <label key={index} className="flex items-start gap-2 text-[12.5px]">
                    <input
                      type="checkbox"
                      checked={selected.has(index)}
                      disabled={outcome === 'CREATED'}
                      onChange={() => toggle(index)}
                      className="mt-0.5"
                    />
                    <span className="txt">
                      <span className="txt-muted">[{item.kind}]</span> {item.description}
                      {outcome && (
                        <span
                          className={`ml-1.5 text-[11px] font-semibold ${
                            outcome === 'CREATED'
                              ? 'text-emerald-600'
                              : outcome === 'SKIPPED'
                                ? 'txt-muted'
                                : 'text-rose-600'
                          }`}
                        >
                          {outcome}
                        </span>
                      )}
                    </span>
                  </label>
                );
              })}
              <button
                type="button"
                onClick={() => void apply()}
                disabled={busy || selected.size === 0}
                className="btn-primary mt-1 inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                Apply selected
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default function AiRecordPanel({
  entityType,
  entityId,
}: {
  entityType: EntityKind;
  entityId: string;
}) {
  const { status, error } = useAiStatus();

  return (
    <div className="space-y-4">
      <AiConnectionNotice status={status} error={error} hideWhenReady />
      <SummaryCard entityType={entityType} entityId={entityId} />
      {entityType === 'ACCOUNT' && <IntelligenceCard entityId={entityId} />}
      {(entityType === 'OPPORTUNITY' || entityType === 'LEAD') && (
        <NextBestActionCard entityType={entityType} entityId={entityId} />
      )}
      {(entityType === 'ACCOUNT' || entityType === 'OPPORTUNITY') && (
        <MeetingExtractionCard entityType={entityType} entityId={entityId} />
      )}
    </div>
  );
}
