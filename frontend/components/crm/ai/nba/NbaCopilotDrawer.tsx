'use client';

import { useState, type ReactNode } from 'react';
import { CheckCircle2, Loader2, RefreshCw, Sparkles } from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormTextarea } from '@/components/crm/forms/FormField';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import AiConnectionNotice from '@/components/crm/ai/AiConnectionNotice';
import AiFeedbackButtons from '@/components/crm/ai/AiFeedbackButtons';
import CopyButton from '@/components/crm/ai/shared/CopyButton';
import { usePermissions } from '@/context/AuthContext';
import { formatCheckedAt, type AiStatus } from '@/features/ai/status';
import type {
  AiGeneration,
  CopilotCallScriptContent,
  CopilotContent,
  CopilotProposalContent,
  NbaAction,
  PriorityScore,
} from '@/features/ai/ai-insights';
import {
  CATEGORY_LABEL,
  CATEGORY_VARIANT,
  COPILOT_LABEL,
  copilotContentOf,
  copilotToText,
  meetingAgendaText,
} from './nba-helpers';
import { RECORD_NOUN } from './nba-view';

/* ============================================================
   NBA COPILOT (Level 3)

   The model drafts what an engine action needs — an email, a
   WhatsApp/LinkedIn message, a meeting invite with agenda, a call
   script or a proposal revision — through `POST /nba/copilot`
   (the AI gateway, grounded in the record's CRM context).

   Nothing is sent or scheduled here. The rep edits the draft and
   approves it, which hands it to the CRM flow that does the work
   (email composer, meeting or task form) where it is saved or sent
   by the rep; a message sent outside the CRM is logged as done.
   ============================================================ */

export type CopilotState =
  | { status: 'loading' }
  | { status: 'ready'; generation: AiGeneration }
  | { status: 'error'; message: string };

export type CopilotApproval =
  | { kind: 'email'; subject: string; body: string }
  | { kind: 'meeting'; title: string; durationMinutes: number; agenda: string }
  | { kind: 'task'; title: string; description: string }
  | { kind: 'done'; note: string };

export interface CopilotTarget {
  item: PriorityScore;
  action: NbaAction;
}

const primaryButton =
  'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50';

function Heading({ children }: { children: string }) {
  return <p className="txt-faint mt-3 text-[10.5px] font-bold uppercase tracking-wider">{children}</p>;
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="mt-1 space-y-1">
      {items.map((line, index) => (
        <li key={`${index}-${line}`} className="txt flex gap-2 text-[12.5px]">
          <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full" style={{ background: 'var(--accent)' }} />
          {line}
        </li>
      ))}
    </ul>
  );
}

function CallScript({ content }: { content: CopilotCallScriptContent }) {
  return (
    <div>
      <Heading>Opening</Heading>
      <p className="txt mt-1 text-[12.5px]">{content.opening}</p>
      <Heading>Questions to ask</Heading>
      <Bullets items={content.questions} />
      <Heading>Talking points</Heading>
      <Bullets items={content.talking_points} />
      {content.objections.length > 0 && (
        <>
          <Heading>Objection handling</Heading>
          <dl className="mt-1 space-y-1.5">
            {content.objections.map((item) => (
              <div key={item.objection} className="text-[12.5px]">
                <dt className="txt font-semibold">“{item.objection}”</dt>
                <dd className="txt-muted">{item.response}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      <Heading>Close</Heading>
      <p className="txt mt-1 text-[12.5px]">{content.close}</p>
    </div>
  );
}

function Proposal({ content }: { content: CopilotProposalContent }) {
  return (
    <div>
      <p className="txt text-[12.5px] leading-relaxed">{content.summary}</p>
      {content.sections.map((section) => (
        <div key={section.title}>
          <Heading>{section.title}</Heading>
          <p className="txt mt-1 whitespace-pre-line text-[12.5px] leading-relaxed">{section.content}</p>
        </div>
      ))}
      {content.next_steps.length > 0 && (
        <>
          <Heading>Next steps</Heading>
          <Bullets items={content.next_steps} />
        </>
      )}
    </div>
  );
}

/** Editable draft plus its approve button — keyed by generation so a regenerate resets the edits. */
function Draft({
  content,
  target,
  onApprove,
}: {
  content: CopilotContent;
  target: CopilotTarget;
  onApprove: (approval: CopilotApproval) => void;
}) {
  const { can } = usePermissions();
  const [subject, setSubject] = useState(content.kind === 'EMAIL' ? content.subject : '');
  const [body, setBody] = useState(content.kind === 'EMAIL' || content.kind === 'MESSAGE' ? content.body : '');
  const [title, setTitle] = useState(content.kind === 'MEETING_AGENDA' ? content.title : target.action.label);
  const [agenda, setAgenda] = useState(content.kind === 'MEETING_AGENDA' ? meetingAgendaText(content) : '');

  const accent = { background: 'var(--accent)' };
  let editor: ReactNode;
  let approve: ReactNode = null;
  let copyValue: string;

  switch (content.kind) {
    case 'EMAIL':
      copyValue = `Subject: ${subject}\n\n${body}`;
      editor = (
        <div className="space-y-3">
          <FormField label="Subject">
            <FormInput value={subject} maxLength={255} onChange={(event) => setSubject(event.target.value)} />
          </FormField>
          <FormField label="Body">
            <FormTextarea rows={12} value={body} onChange={(event) => setBody(event.target.value)} />
          </FormField>
        </div>
      );
      if (can('emails', 'CREATE')) {
        approve = (
          <button
            type="button"
            className={primaryButton}
            style={accent}
            disabled={!subject.trim() || !body.trim()}
            onClick={() => onApprove({ kind: 'email', subject: subject.trim(), body })}
          >
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Approve & open composer
          </button>
        );
      }
      break;
    case 'MESSAGE':
      copyValue = body;
      editor = (
        <FormField label="Message">
          <FormTextarea rows={8} value={body} onChange={(event) => setBody(event.target.value)} />
        </FormField>
      );
      approve = (
        <button
          type="button"
          className={primaryButton}
          style={accent}
          disabled={!body.trim()}
          onClick={() => onApprove({ kind: 'done', note: `Sent: ${target.action.label}` })}
        >
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Approve — I sent it
        </button>
      );
      break;
    case 'MEETING_AGENDA':
      copyValue = `${title}\n\n${agenda}`;
      editor = (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={`${content.duration_minutes} minutes`} variant="neutral" />
          </div>
          <FormField label="Invite title">
            <FormInput value={title} maxLength={255} onChange={(event) => setTitle(event.target.value)} />
          </FormField>
          <FormField label="Description & agenda">
            <FormTextarea rows={12} value={agenda} onChange={(event) => setAgenda(event.target.value)} />
          </FormField>
        </div>
      );
      if (can('activities', 'CREATE')) {
        approve = (
          <button
            type="button"
            className={primaryButton}
            style={accent}
            disabled={!title.trim()}
            onClick={() =>
              onApprove({ kind: 'meeting', title: title.trim(), durationMinutes: content.duration_minutes, agenda })
            }
          >
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Approve & schedule
          </button>
        );
      }
      break;
    case 'CALL_SCRIPT':
    case 'PROPOSAL':
      copyValue = copilotToText(content);
      editor = content.kind === 'CALL_SCRIPT' ? <CallScript content={content} /> : <Proposal content={content} />;
      if (can('tasks', 'CREATE')) {
        approve = (
          <button
            type="button"
            className={primaryButton}
            style={accent}
            onClick={() => onApprove({ kind: 'task', title: target.action.label, description: copilotToText(content) })}
          >
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Approve & add task
          </button>
        );
      }
      break;
  }

  return (
    <div className="space-y-3">
      <div className="surface bd rounded-2xl border p-4">{editor}</div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <CopyButton value={copyValue} label="Copy draft" showLabel />
        {approve}
      </div>
    </div>
  );
}

export default function NbaCopilotDrawer({
  target,
  state,
  onGenerate,
  onApprove,
  onClose,
  aiStatus,
  aiError,
  aiReady,
  canUseAi,
}: {
  target: CopilotTarget | null;
  state: CopilotState | null;
  onGenerate: (instruction: string | null) => void;
  onApprove: (approval: CopilotApproval, generation: AiGeneration) => void;
  onClose: () => void;
  aiStatus: AiStatus | null;
  aiError: string | null;
  aiReady: boolean;
  canUseAi: boolean;
}) {
  const [instruction, setInstruction] = useState('');
  if (!target) return null;

  const { item, action } = target;
  const generation = state?.status === 'ready' ? state.generation : null;
  const content = copilotContentOf(generation);
  const mayAsk = aiReady && canUseAi;
  const kindLabel = action.copilot ? COPILOT_LABEL[action.copilot] : 'Draft';

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title={`Copilot · ${kindLabel}`}
      subtitle={`${action.label} — ${RECORD_NOUN[item.entity_type].toLowerCase()} ${item.entity_label}`}
      width="max-w-2xl"
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={CATEGORY_LABEL[action.category]} variant={CATEGORY_VARIANT[action.category]} />
          <span className="txt-muted text-[12px]">Nothing is sent or scheduled until you approve it and save.</span>
        </div>

        {!aiReady && (
          <AiConnectionNotice
            status={aiStatus}
            error={aiError}
            hideWhenReady
            compact
            consequence="The Copilot drafts through the AI connection; the action itself can still be carried out by hand."
          />
        )}

        <section className="surface bd rounded-2xl border p-4">
          <FormField label="Guidance for the draft (optional)">
            <FormInput
              value={instruction}
              maxLength={1000}
              placeholder="e.g. mention the manufacturing case study and propose Thursday"
              onChange={(event) => setInstruction(event.target.value)}
            />
          </FormField>
          <div className="mt-2 flex justify-end">
            <button
              type="button"
              disabled={!mayAsk || state?.status === 'loading'}
              onClick={() => onGenerate(instruction.trim() || null)}
              className="ctl inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {state?.status === 'loading' ? (
                <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
              ) : generation ? (
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {state?.status === 'loading' ? 'Drafting…' : generation ? 'Regenerate' : 'Draft'}
            </button>
          </div>
        </section>

        {state?.status === 'loading' && (
          <p role="status" aria-busy="true" className="txt-muted flex items-center gap-2 text-[12.5px]">
            <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> The Copilot is drafting from
            this record’s CRM context…
          </p>
        )}
        {state?.status === 'error' && (
          <p role="alert" className="text-[12.5px] text-rose-600">
            {state.message}
          </p>
        )}
        {generation && !content && (
          <p role="alert" className="text-[12.5px] text-rose-600">
            The model did not return a usable draft. Try again, or carry the action out by hand.
          </p>
        )}

        {generation && content && (
          <>
            <Draft
              key={generation.id}
              content={content}
              target={target}
              onApprove={(approval) => onApprove(approval, generation)}
            />
            <div className="flex items-center justify-between gap-2">
              <p className="txt-faint text-[11px]">
                Drafted {formatCheckedAt(generation.created_at) || 'just now'}
                {generation.model ? ` · ${generation.model}` : ''}
                {!generation.used_crm_context && ' · without CRM context'}
              </p>
              <AiFeedbackButtons key={generation.id} generation={generation} />
            </div>
          </>
        )}
      </div>
    </SlideDrawer>
  );
}
