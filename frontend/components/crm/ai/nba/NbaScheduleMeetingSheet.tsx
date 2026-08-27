'use client';

import { useState } from 'react';
import { Info } from 'lucide-react';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormTextarea } from '@/components/crm/forms/FormField';
import { DEMO_TODAY } from '@/features/ai/shared/format';
import type { NbaRecord } from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA SCHEDULE MEETING SHEET
   Lightweight demo scheduler using the CRM's existing drawer
   and form primitives. Submitting updates local state and
   shows a confirmation — no calendar event is created.
   ============================================================ */

interface MeetingForm {
  title: string;
  date: string;
  time: string;
  participants: string;
  notes: string;
}

interface NbaScheduleMeetingSheetProps {
  open: boolean;
  record: NbaRecord | null;
  onClose: () => void;
  /** Called on submit so the page can update status and raise a toast. */
  onSchedule: (record: NbaRecord, form: MeetingForm) => void;
}

/** The form as it stands before anyone types: derived from the record. */
function prefill(record: NbaRecord): MeetingForm {
  return {
    title: record.recommendation,
    date: record.nextFollowUp || DEMO_TODAY,
    time: '10:00',
    participants: `${record.leadName}, ${record.assignedTo}`,
    notes: record.reason,
  };
}

export default function NbaScheduleMeetingSheet({
  open,
  record,
  onClose,
  onSchedule,
}: NbaScheduleMeetingSheetProps) {
  /* Only what the user has actually changed is stored, tagged with the record
     it was typed against. The sheet opening for a different record therefore
     resets itself by derivation — no effect writing state on open, which
     costs a second render and briefly shows the previous lead's details in
     the fields. `null` means untouched: show the prefill. */
  const [draft, setDraft] = useState<
    { recordId: string; form: MeetingForm; touched: boolean } | null
  >(null);

  if (!record) return null;

  const isDraftForThisRecord = draft?.recordId === record.id;
  const form = isDraftForThisRecord ? draft.form : prefill(record);
  const touched = isDraftForThisRecord ? draft.touched : false;

  const titleMissing = form.title.trim().length === 0;
  const dateMissing = form.date.trim().length === 0;

  const handleSubmit = () => {
    setDraft({ recordId: record.id, form, touched: true });
    if (titleMissing || dateMissing) return;
    onSchedule(record, form);
  };

  const update = <K extends keyof MeetingForm>(key: K, value: MeetingForm[K]) =>
    setDraft({ recordId: record.id, form: { ...form, [key]: value }, touched });

  return (
    <SlideDrawer
      open={open}
      onClose={onClose}
      title="Schedule Meeting"
      subtitle={`${record.leadName} · ${record.company}`}
      width="max-w-lg"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            className="rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            Schedule
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField
          label="Meeting title"
          htmlFor="nba-meeting-title"
          required
          error={touched && titleMissing ? 'A meeting title is required' : undefined}
        >
          <FormInput
            id="nba-meeting-title"
            value={form.title}
            hasError={touched && titleMissing}
            onChange={event => update('title', event.target.value)}
            placeholder="e.g. Commercial review with finance"
          />
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Date"
            htmlFor="nba-meeting-date"
            required
            error={touched && dateMissing ? 'Select a date' : undefined}
          >
            <FormInput
              id="nba-meeting-date"
              type="date"
              value={form.date}
              hasError={touched && dateMissing}
              onChange={event => update('date', event.target.value)}
            />
          </FormField>

          <FormField label="Time" htmlFor="nba-meeting-time">
            <FormInput
              id="nba-meeting-time"
              type="time"
              value={form.time}
              onChange={event => update('time', event.target.value)}
            />
          </FormField>
        </div>

        <FormField label="Participants" htmlFor="nba-meeting-participants">
          <FormInput
            id="nba-meeting-participants"
            value={form.participants}
            onChange={event => update('participants', event.target.value)}
            placeholder="Comma-separated names"
          />
        </FormField>

        <FormField label="Notes" htmlFor="nba-meeting-notes">
          <FormTextarea
            id="nba-meeting-notes"
            value={form.notes}
            onChange={event => update('notes', event.target.value)}
            rows={4}
          />
        </FormField>

        <p className="txt-muted flex items-start gap-2 text-[12px] leading-relaxed">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
          Scheduling updates this recommendation locally for the demonstration. No calendar invitation
          is created and nothing is saved to a server.
        </p>
      </div>
    </SlideDrawer>
  );
}
