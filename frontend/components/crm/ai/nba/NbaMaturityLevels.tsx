import { ChevronRight, History, Sparkles, Workflow, type LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';

/* ============================================================
   NBA MATURITY LEVELS

   How the queue's recommendations are made, as the three steps
   they build on — each with what it is producing right now:

   1. Rule-based   conditions over CRM signals (the rules engine)
   2. Predictive   what similar won deals did at this point
   3. Copilot      the model drafts the email, invite, agenda,
                   call script or proposal; the rep approves
   ============================================================ */

function Step({
  level,
  icon: Icon,
  title,
  detail,
  stat,
  muted,
}: {
  level: number;
  icon: LucideIcon;
  title: string;
  detail: string;
  stat: string;
  muted?: boolean;
}) {
  return (
    <li className={cn('surface bd flex min-w-0 flex-1 items-start gap-3 rounded-2xl border p-3.5', muted && 'opacity-75')}>
      <span
        className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white"
        style={{ background: 'var(--accent)' }}
        aria-hidden="true"
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Level {level}</p>
        <p className="txt font-display text-[13.5px] font-bold">{title}</p>
        <p className="txt-muted text-[12px] leading-snug">{detail}</p>
        <p className="mt-1 text-[12px] font-semibold" style={{ color: 'var(--accent)' }}>
          {stat}
        </p>
      </div>
    </li>
  );
}

export default function NbaMaturityLevels({
  ruleActions,
  predictiveActions,
  copilotActions,
  copilotReady,
}: {
  ruleActions: number;
  predictiveActions: number;
  /** Queued actions the Copilot can draft for. */
  copilotActions: number;
  copilotReady: boolean;
}) {
  const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`;
  return (
    <ol aria-label="How recommendations are made" className="flex flex-col gap-2 md:flex-row md:items-stretch">
      <Step
        level={1}
        icon={Workflow}
        title="Rule-based"
        detail="If a CRM signal crosses a rule’s threshold, recommend its action."
        stat={`${plural(ruleActions, 'action')} in the queue`}
      />
      <ChevronRight className="txt-faint hidden h-4 w-4 shrink-0 self-center md:block" aria-hidden="true" />
      <Step
        level={2}
        icon={History}
        title="Predictive"
        detail="Deals like this one were won when this step came next."
        stat={predictiveActions > 0 ? `${plural(predictiveActions, 'action')} in the queue` : 'Needs closed-deal history'}
        muted={predictiveActions === 0}
      />
      <ChevronRight className="txt-faint hidden h-4 w-4 shrink-0 self-center md:block" aria-hidden="true" />
      <Step
        level={3}
        icon={Sparkles}
        title="Generative Copilot"
        detail="Drafts the email, invite, agenda, call script or proposal. You approve it."
        stat={copilotReady ? `${plural(copilotActions, 'action')} ready to draft` : 'Needs the AI connection'}
        muted={!copilotReady}
      />
    </ol>
  );
}
