import type { ReactNode } from 'react';
import { CheckCircle2, ListChecks, Sparkles, Zap } from 'lucide-react';

import StatusBadge from '@/components/crm/shared/StatusBadge';
import { formatCheckedAt } from '@/features/ai/status';
import { cn } from '@/lib/utils';
import { LEVEL_VARIANT, type Recommendation } from './nba-view';

/* ============================================================
   NBA RECOMMENDATION

   The one visual for an AI Next Best Action, used by the global
   queue, its Explain drawer and the Opportunity/Lead 360 panel,
   so a recommendation reads the same wherever it appears.

   It renders a stored generation verbatim — action, why, urgency,
   evidence, suggested steps — and always says when it was
   generated, because a cached answer can predate the record's
   latest activity.
   ============================================================ */

const URGENCY_LABEL = { HIGH: 'High urgency', MEDIUM: 'Medium urgency', LOW: 'Low urgency' } as const;

export function NbaRecommendationBlock({
  recommendation,
  compact = false,
  headerAside,
  footer,
}: {
  recommendation: Recommendation;
  /** Queue rows: action and a clamped why only. */
  compact?: boolean;
  headerAside?: ReactNode;
  footer?: ReactNode;
}) {
  const { content, generation } = recommendation;
  const generatedAt = formatCheckedAt(generation.created_at);

  return (
    <section
      className="rounded-xl border p-3.5 sm:p-4"
      style={{ background: 'var(--accent-soft)', borderColor: 'color-mix(in srgb, var(--accent) 35%, transparent)' }}
      aria-label="AI recommendation"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p
          className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wider"
          style={{ color: 'var(--accent)' }}
        >
          <Zap className="h-3.5 w-3.5" aria-hidden="true" />
          Recommended action
        </p>
        <div className="flex items-center gap-2">
          <StatusBadge label={URGENCY_LABEL[content.urgency]} variant={LEVEL_VARIANT[content.urgency]} />
          {headerAside}
        </div>
      </div>

      <p className={cn('txt font-display mt-2 font-bold leading-snug', compact ? 'text-[14px]' : 'text-[15.5px]')}>
        {content.action}
      </p>

      <p className={cn('txt-muted mt-1.5 text-[12.5px] leading-relaxed', compact && 'line-clamp-2')}>
        <span className="txt font-semibold">Why: </span>
        {content.why}
      </p>

      {!compact && content.evidence.length > 0 && (
        <div className="mt-3">
          <p className="txt-faint flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wider">
            <ListChecks className="h-3.5 w-3.5" aria-hidden="true" /> CRM evidence cited
          </p>
          <ul className="mt-1.5 space-y-1">
            {content.evidence.map((item, index) => (
              <li key={`${index}-${item}`} className="txt flex gap-2 text-[12.5px]">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full" style={{ background: 'var(--accent)' }} />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!compact && content.suggested_actions.length > 0 && (
        <div className="mt-3">
          <p className="txt-faint flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wider">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Suggested next steps
          </p>
          <ol className="mt-1.5 space-y-1">
            {content.suggested_actions.map((step, index) => (
              <li key={`${index}-${step}`} className="txt flex gap-2 text-[12.5px]">
                <span className="txt-faint w-4 shrink-0 text-right font-semibold">{index + 1}.</span>
                {step}
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="txt-faint text-[11px]">
          Generated {generatedAt || 'earlier'}
          {generation.model ? ` · ${generation.model}` : ''}
          {!generation.used_crm_context && ' · without CRM context'}
        </p>
        {footer}
      </div>
    </section>
  );
}

/** No generation stored yet — says so plainly, never a placeholder action. */
export function NbaNoRecommendation({
  children,
  note,
}: {
  /** The Generate button, when the caller may and AI is ready. */
  children?: ReactNode;
  note?: string;
}) {
  return (
    <section
      className="bd flex flex-col gap-2.5 rounded-xl border border-dashed p-3.5 sm:flex-row sm:items-center sm:justify-between sm:p-4"
      aria-label="AI recommendation"
    >
      <div className="min-w-0">
        <p className="txt flex items-center gap-1.5 text-[12.5px] font-semibold">
          <Sparkles className="txt-faint h-3.5 w-3.5" aria-hidden="true" />
          No AI recommendation yet
        </p>
        {note && <p className="txt-muted mt-0.5 text-[12px]">{note}</p>}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </section>
  );
}
