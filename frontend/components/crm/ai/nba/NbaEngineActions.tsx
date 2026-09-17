'use client';

import { useState } from 'react';
import { Check, ChevronDown, Clock, History, Loader2, Sparkles, X } from 'lucide-react';

import StatusBadge from '@/components/crm/shared/StatusBadge';
import type { NbaAction, PriorityScore } from '@/features/ai/ai-insights';
import { cn } from '@/lib/utils';
import {
  CATEGORY_ICON,
  CATEGORY_LABEL,
  CATEGORY_VARIANT,
  COPILOT_LABEL,
  EXECUTION_ICON,
  EXECUTION_VERB,
  LEVEL_LABEL,
  PRIORITY_LABEL,
  PRIORITY_VARIANT,
  confidenceLabel,
} from './nba-helpers';

/* ============================================================
   NBA ENGINE ACTIONS

   The engine's recommended actions for one record, best first,
   exactly as `GET /priority/*` or `GET /nba/*` returned them:

   - Level 1 (Rule-based): a rules-engine condition matched.
   - Level 2 (Predictive): similar won deals took this step here;
     the confidence is the measured share, never an estimate.
   - Level 3 (Copilot): the "Draft" button — the model prepares the
     email, invite, agenda, call script or proposal for review.

   Each action can be carried out through an existing CRM flow,
   drafted by the Copilot, marked done or dismissed. Done and
   dismissed are logged (`POST /nba/actions/log`) so the rule's
   cooldown keeps it from coming straight back.
   ============================================================ */

export type NbaLogOutcome = 'EXECUTED' | 'DISMISSED';

export interface NbaEngineHandlers {
  /** AI ready and `ai_insights.CREATE` held. */
  canCopilot: boolean;
  /** `ai_insights.CREATE` — logging an outcome. */
  canLog: boolean;
  /** `${entity_id}:${action_code}` currently being logged. */
  logging: ReadonlySet<string>;
  onRun: (item: PriorityScore, action: NbaAction) => void;
  onCopilot: (item: PriorityScore, action: NbaAction) => void;
  onLog: (item: PriorityScore, action: NbaAction, outcome: NbaLogOutcome) => void;
}

export const logKey = (item: Pick<PriorityScore, 'entity_id'>, action: Pick<NbaAction, 'action_code'>) =>
  `${item.entity_id}:${action.action_code}`;

const iconButton =
  'inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50';

function ActionRow({
  item,
  action,
  handlers,
  detailed,
  primary,
}: {
  item: PriorityScore;
  action: NbaAction;
  handlers?: NbaEngineHandlers;
  detailed: boolean;
  primary: boolean;
}) {
  const CategoryIcon = CATEGORY_ICON[action.category];
  const ExecIcon = EXECUTION_ICON[action.execution];
  const busy = handlers?.logging.has(logKey(item, action)) ?? false;
  const reasons = detailed ? action.reasons : action.reasons.slice(0, 1);

  return (
    <div
      className={cn('rounded-xl border p-3', primary ? '' : 'bd')}
      style={
        primary
          ? { background: 'var(--accent-soft)', borderColor: 'color-mix(in srgb, var(--accent) 35%, transparent)' }
          : undefined
      }
      data-action-code={action.action_code}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusBadge label={CATEGORY_LABEL[action.category]} variant={CATEGORY_VARIANT[action.category]} />
        <StatusBadge label={PRIORITY_LABEL[action.priority]} variant={PRIORITY_VARIANT[action.priority]} />
        <span
          className="txt-faint inline-flex items-center gap-1 text-[11px] font-semibold"
          title={
            action.level === 'PREDICTIVE'
              ? 'Level 2 — learned from how similar deals were won'
              : 'Level 1 — a rules-engine condition matched'
          }
        >
          {action.level === 'PREDICTIVE' && <History className="h-3 w-3" aria-hidden="true" />}
          {LEVEL_LABEL[action.level]}
          {action.confidence !== null && ` · ${action.confidence}% (${confidenceLabel(action.confidence).toLowerCase()})`}
        </span>
      </div>

      <p className={cn('txt font-display mt-1.5 flex items-start gap-1.5 font-bold leading-snug', primary ? 'text-[14px]' : 'text-[13px]')}>
        <CategoryIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
        {action.label}
      </p>

      {reasons.length > 0 && (
        <div className="txt-muted mt-1 space-y-0.5 text-[12px] leading-relaxed">
          {reasons.map((reason) => (
            <p key={reason}>{reason}</p>
          ))}
        </div>
      )}

      {action.timing && (
        <p className="mt-1 flex items-center gap-1 text-[11.5px] font-semibold text-amber-700 dark:text-amber-300">
          <Clock className="h-3 w-3" aria-hidden="true" /> {action.timing}
        </p>
      )}

      {detailed && action.signals.length > 0 && (
        <dl className="bd mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t pt-2 sm:grid-cols-3">
          {action.signals.map((signal) => (
            <div key={signal.key} className="min-w-0">
              <dt className="txt-faint truncate text-[10.5px] font-bold uppercase tracking-wider">{signal.label}</dt>
              <dd className="txt truncate text-[12px] font-medium">{signal.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {handlers && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => handlers.onRun(item, action)}
            className={cn(iconButton, 'text-white hover:opacity-90')}
            style={{ background: 'var(--accent)' }}
          >
            <ExecIcon className="h-3.5 w-3.5" aria-hidden="true" />
            {EXECUTION_VERB[action.execution]}
          </button>
          {action.copilot && handlers.canCopilot && (
            <button
              type="button"
              onClick={() => handlers.onCopilot(item, action)}
              className={cn(iconButton, 'ctl hover:opacity-80')}
            >
              <Sparkles className="h-3.5 w-3.5" style={{ color: 'var(--accent)' }} aria-hidden="true" />
              {COPILOT_LABEL[action.copilot]}
            </button>
          )}
          {handlers.canLog && (
            <span className="ml-auto flex items-center gap-1">
              {busy && <Loader2 className="txt-faint h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
              <button
                type="button"
                disabled={busy}
                onClick={() => handlers.onLog(item, action, 'EXECUTED')}
                className={cn(iconButton, 'txt-muted hover:bg-[var(--surface-2)] hover:text-[var(--text)]')}
                aria-label={`Mark “${action.label}” done`}
              >
                <Check className="h-3.5 w-3.5" aria-hidden="true" /> Done
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => handlers.onLog(item, action, 'DISMISSED')}
                className={cn(iconButton, 'txt-muted hover:bg-[var(--surface-2)] hover:text-[var(--text)]')}
                aria-label={`Dismiss “${action.label}”`}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" /> Dismiss
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function NbaEngineActions({
  item,
  handlers,
  detailed = false,
}: {
  item: PriorityScore;
  /** Omitted for a read-only list (the record page links to the queue instead). */
  handlers?: NbaEngineHandlers;
  /** Every reason and the signal evidence (drawer); otherwise the top action leads. */
  detailed?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const actions = item.actions;

  if (actions.length === 0) {
    return (
      <p className="txt-muted bd rounded-xl border border-dashed p-3 text-[12.5px]">
        No engine action right now — no rule matches this record, or its actions are cooling down after being
        done or dismissed.
      </p>
    );
  }

  const [first, ...rest] = actions;
  const showRest = detailed || expanded;

  return (
    <div className="space-y-2" role="group" aria-label="Next best actions">
      <ActionRow item={item} action={first} handlers={handlers} detailed={detailed} primary />
      {rest.length > 0 && !detailed && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          className="txt-muted inline-flex items-center gap-1 text-[12px] font-semibold transition hover:text-[var(--text)]"
        >
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} aria-hidden="true" />
          {expanded ? 'Fewer actions' : `${rest.length} more action${rest.length === 1 ? '' : 's'}`}
        </button>
      )}
      {showRest &&
        rest.map((action) => (
          <ActionRow
            key={action.action_code}
            item={item}
            action={action}
            handlers={handlers}
            detailed={detailed}
            primary={false}
          />
        ))}
    </div>
  );
}
