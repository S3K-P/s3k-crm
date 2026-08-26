import { cn } from '@/lib/utils';
import { Clock, Building2, User } from 'lucide-react';

/* ============================================================
   MEETING CARD
   Compact meeting item with time, company, contact, and status.
   Reusable in Dashboard, Meetings list, Lead detail, etc.
   ============================================================ */

export type MeetingStatus = 'upcoming' | 'in-progress' | 'completed' | 'cancelled';

export interface MeetingItem {
  id: string;
  title: string;
  /** e.g. "10:00 AM – 10:30 AM" */
  time: string;
  /** Omitted when the meeting is not linked to a company. */
  company?: string;
  /** Omitted when no contact is attached. */
  contact?: string;
  status: MeetingStatus;
}

interface MeetingCardProps {
  meeting: MeetingItem;
  className?: string;
}

const statusConfig: Record<MeetingStatus, { label: string; bg: string; color: string }> = {
  'upcoming':    { label: 'Upcoming',    bg: '#eff6ff', color: '#2563eb' },
  'in-progress': { label: 'In Progress', bg: '#ecfdf5', color: '#059669' },
  'completed':   { label: 'Completed',   bg: 'var(--surface-2)', color: 'var(--muted)' },
  'cancelled':   { label: 'Cancelled',   bg: '#fef2f2', color: '#dc2626' },
};

export default function MeetingCard({ meeting, className }: MeetingCardProps) {
  const s = statusConfig[meeting.status];

  return (
    <div className={cn(
      'surface bd rounded-xl border p-3.5 transition-all hover:shadow-sm',
      className,
    )}>
      <div className="flex items-start justify-between gap-2">
        <h4 className="txt text-[13px] font-semibold leading-tight">{meeting.title}</h4>
        <span
          className="shrink-0 rounded-full px-2 py-[2px] text-[10px] font-bold"
          style={{ background: s.bg, color: s.color }}
        >
          {s.label}
        </span>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="txt-muted flex items-center gap-1.5 text-[12px]">
          <Clock className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
          {meeting.time}
        </span>
        {/* Omitted rather than shown blank: a meeting with nothing linked to it
            is a real state, and an empty icon row implies missing data. */}
        {meeting.company && (
          <span className="txt-muted flex items-center gap-1.5 text-[12px]">
            <Building2 className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
            {meeting.company}
          </span>
        )}
        {meeting.contact && (
          <span className="txt-muted flex items-center gap-1.5 text-[12px]">
            <User className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
            {meeting.contact}
          </span>
        )}
      </div>
    </div>
  );
}
