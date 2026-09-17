'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import { FormError } from '@/components/crm/shared/ListStates';
import { notifySuccess } from '@/components/crm/feedback/notify';
import { useMutation } from '@/features/shared/hooks/useCollection';
import { createMeeting } from '@/features/crm/meetings';
import { MEETING_TYPES, type MeetingType } from '@/features/crm/activities';
import { createTask, TASK_PRIORITIES, type Priority } from '@/features/crm/tasks';
import type { PriorityScore } from '@/features/ai/ai-insights';
import { humanize } from '@/components/crm/shared/statusVariants';
import { RECORD_NOUN, recommendationOf } from './nba-view';

/* ============================================================
   NBA ACTION DRAWERS

   "Take action" for a task or a meeting, filed against the ranked
   record through the same endpoints the Tasks and Meetings pages
   use. Pre-filled from the stored AI recommendation when there is
   one — every field stays editable, and nothing is written until
   the rep saves.

   Mounted only while open (the ComposeEmailDrawer pattern), so a
   cancelled form never leaks into the next record's.
   ============================================================ */

/** Backend limit on task titles and activity subjects. */
const TITLE_MAX = 255;

const clip = (text: string) => (text.length > TITLE_MAX ? `${text.slice(0, TITLE_MAX - 1)}…` : text);

/** `datetime-local` value -> ISO instant, or `null` when blank or invalid. */
function toInstant(local: string): string | null {
  if (!local) return null;
  const parsed = new Date(local);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

interface DrawerProps {
  item: PriorityScore | null;
  onClose: () => void;
  /** After a successful save — the queue refreshes its facts. */
  onSaved: () => void;
}

/* ---- Follow-up task ------------------------------------------------------ */

export function NbaTaskDrawer(props: DrawerProps) {
  if (!props.item) return null;
  return <TaskForm {...props} item={props.item} />;
}

function TaskForm({ item, onClose, onSaved }: DrawerProps & { item: PriorityScore }) {
  const recommendation = recommendationOf(item.latest_recommendation);
  const [title, setTitle] = useState(
    clip(recommendation?.content.action ?? `Follow up: ${item.entity_label}`),
  );
  const [description, setDescription] = useState(recommendation?.content.why ?? '');
  const [dueDate, setDueDate] = useState('');
  const [priority, setPriority] = useState<Priority>(item.level);
  const { pending, error, run } = useMutation();

  const save = async () => {
    if (!title.trim()) return;
    const saved = await run(() =>
      createTask({
        title: title.trim(),
        description: description.trim() || null,
        priority,
        due_date: toInstant(dueDate),
        related_entity_type: item.entity_type,
        related_entity_id: item.entity_id,
      }),
    );
    if (saved === undefined) return;
    notifySuccess('Follow-up task created', title.trim());
    onSaved();
    onClose();
  };

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title="Create follow-up task"
      subtitle={`Filed against ${RECORD_NOUN[item.entity_type].toLowerCase()} ${item.entity_label}.`}
      width="max-w-lg"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="ctl px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={pending || !title.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
            Create task
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField label="Title" required>
          <FormInput value={title} maxLength={TITLE_MAX} onChange={(event) => setTitle(event.target.value)} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Due">
            <FormInput type="datetime-local" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
          </FormField>
          <FormField label="Priority">
            <FormSelect
              value={priority}
              onChange={(event) => setPriority(event.target.value as Priority)}
              options={TASK_PRIORITIES.map((value) => ({ value, label: humanize(value) }))}
            />
          </FormField>
        </div>
        <FormField label="Description">
          <FormTextarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} />
        </FormField>
        {recommendation && (
          <p className="txt-faint text-[11.5px]">Pre-filled from the stored AI recommendation — edit freely.</p>
        )}
        <FormError message={error} />
      </div>
    </SlideDrawer>
  );
}

/* ---- Meeting ------------------------------------------------------------- */

const DURATIONS = [15, 30, 45, 60, 90];

export function NbaMeetingDrawer(props: DrawerProps) {
  if (!props.item) return null;
  return <MeetingForm {...props} item={props.item} />;
}

function MeetingForm({ item, onClose, onSaved }: DrawerProps & { item: PriorityScore }) {
  const recommendation = recommendationOf(item.latest_recommendation);
  const [subject, setSubject] = useState(
    clip(recommendation?.content.action ?? `Meeting: ${item.entity_label}`),
  );
  const [startTime, setStartTime] = useState('');
  const [duration, setDuration] = useState('30');
  const [meetingType, setMeetingType] = useState<MeetingType>('VIDEO');
  const [link, setLink] = useState('');
  const [location, setLocation] = useState('');
  const [agenda, setAgenda] = useState(recommendation?.content.suggested_actions.join('\n') ?? '');
  const [validation, setValidation] = useState<string | null>(null);
  const { pending, error, run } = useMutation();

  const save = async () => {
    const startsAt = toInstant(startTime);
    if (!subject.trim() || startsAt === null) {
      setValidation('A title and a start time are required.');
      return;
    }
    setValidation(null);
    const endsAt = new Date(new Date(startsAt).getTime() + Number(duration) * 60_000).toISOString();
    const saved = await run(() =>
      createMeeting({
        subject: subject.trim(),
        related_entity_type: item.entity_type,
        related_entity_id: item.entity_id,
        meeting: {
          meeting_type: meetingType,
          start_time: startsAt,
          end_time: endsAt,
          meeting_link: link.trim() || null,
          location: location.trim() || null,
          agenda: agenda.trim() || null,
        },
      }),
    );
    if (saved === undefined) return;
    notifySuccess('Meeting scheduled', subject.trim());
    onSaved();
    onClose();
  };

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title="Schedule a meeting"
      subtitle={`Filed against ${RECORD_NOUN[item.entity_type].toLowerCase()} ${item.entity_label}. The CRM sends no invitations.`}
      width="max-w-lg"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="ctl px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={pending || !subject.trim() || !startTime}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
            Schedule meeting
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField label="Title" required>
          <FormInput value={subject} maxLength={TITLE_MAX} onChange={(event) => setSubject(event.target.value)} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Starts" required>
            <FormInput type="datetime-local" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
          </FormField>
          <FormField label="Duration">
            <FormSelect
              value={duration}
              onChange={(event) => setDuration(event.target.value)}
              options={DURATIONS.map((minutes) => ({ value: String(minutes), label: `${minutes} minutes` }))}
            />
          </FormField>
        </div>
        <FormField label="Type">
          <FormSelect
            value={meetingType}
            onChange={(event) => setMeetingType(event.target.value as MeetingType)}
            options={MEETING_TYPES.map((value) => ({ value, label: humanize(value) }))}
          />
        </FormField>
        {meetingType === 'IN_PERSON' ? (
          <FormField label="Location">
            <FormInput value={location} maxLength={255} onChange={(event) => setLocation(event.target.value)} />
          </FormField>
        ) : (
          <FormField label="Meeting link">
            <FormInput
              type="url"
              value={link}
              maxLength={1024}
              placeholder="https://"
              onChange={(event) => setLink(event.target.value)}
            />
          </FormField>
        )}
        <FormField label="Agenda">
          <FormTextarea rows={4} value={agenda} onChange={(event) => setAgenda(event.target.value)} />
        </FormField>
        {recommendation && (
          <p className="txt-faint text-[11.5px]">Pre-filled from the stored AI recommendation — edit freely.</p>
        )}
        <FormError message={validation ?? error} />
      </div>
    </SlideDrawer>
  );
}
