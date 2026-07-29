'use client';

import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Calendar as CalendarIcon, Building2, Phone, Mail, FileText, CheckCircle2, Video, Plus, Target, CheckSquare, Sparkles } from 'lucide-react';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import Tabs, { type TabDef } from '@/components/crm/shared/Tabs';
import AIMeetingAssistant, { type AIMeetingAssistantData } from '@/components/crm/ai/AIMeetingAssistant';
import ActivityItem from '@/components/crm/cards/ActivityItem';

/* ============================================================
   MOCK DATA
   ============================================================ */
const MOCK_MEETING = {
  id: '1',
  title: 'Q3 Enterprise Proposal Review',
  type: 'Online',
  date: '2026-07-15',
  startTime: '10:00 AM',
  endTime: '11:00 AM',
  participants: 'Sarah Chen, John Doe',
  internalParticipants: 'Mike Johnson, Sales Engineering',
  account: 'Acme Corp',
  opportunity: 'Enterprise Expansion - Q3',
  owner: 'Mike Johnson',
  location: 'Zoom',
  link: 'https://zoom.us/j/123456',
  agenda: '1. Introduction\n2. Review Proposal\n3. Q&A\n4. Next Steps',
  status: 'Completed',
};

const MOCK_AI_DATA: AIMeetingAssistantData = {
  summary: 'The meeting focused on the Q3 Enterprise Expansion proposal. The client was receptive but requested additional details regarding the implementation timeline and data security protocols.',
  actionItems: [
    'Send detailed implementation timeline by Friday.',
    'Provide the security whitepaper to John Doe.',
    'Schedule a follow-up call with the technical team.'
  ],
  customerSentiment: 'Positive',
  risksDiscussed: 'Potential delays in their internal legal review process which might push the deal to Q4.',
  suggestedNextSteps: 'Send the requested documents immediately and book the technical follow-up.',
  emailDraftSnippet: 'Hi Sarah,\n\nThank you for the productive call today. As discussed, I have attached the implementation timeline and our security whitepaper...\n\nBest,\nMike',
};

const MOCK_ACTIVITIES = [
  { id: '1', icon: Video, iconGradient: 'from-sky-500 to-blue-600', title: 'Meeting Started', detail: 'Joined by 3 participants.', timestamp: '2 hours ago' },
  { id: '2', icon: FileText, iconGradient: 'from-amber-500 to-orange-500', title: 'Note Added', detail: '"Client requested security docs."', timestamp: '1 hour ago' },
  { id: '3', icon: CheckCircle2, iconGradient: 'from-emerald-500 to-green-600', title: 'Meeting Completed', detail: 'Marked as completed by Mike.', timestamp: '30 mins ago' },
];

/* ============================================================
   PAGE COMPONENT
   ============================================================ */

export default function MeetingDetailsPage() {
  const router = useRouter();
  const { id } = useParams();
  
  // Real app would fetch meeting by id here.
  const meeting = MOCK_MEETING;

  const tabs: TabDef[] = [
    {
      id: 'overview',
      label: 'Overview',
      content: (
        <div className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Meeting Details" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Date & Time</p><p className="txt text-[13.5px] mt-1 font-medium">{meeting.date} ({meeting.startTime} - {meeting.endTime})</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Location</p><p className="txt text-[13.5px] mt-1">{meeting.location}</p></div>
                <div>
                  <p className="txt-muted text-[12px] font-semibold uppercase">Link</p>
                  <p className="txt text-[13.5px] mt-1"><a href={meeting.link} target="_blank" rel="noreferrer" className="text-[var(--accent)] hover:underline">{meeting.link}</a></p>
                </div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Owner</p><p className="txt text-[13.5px] mt-1">{meeting.owner}</p></div>
              </div>
            </div>
            
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Participants" />
              <div className="space-y-4 pt-2">
                <div><p className="txt-muted text-[12px] font-semibold uppercase">External</p><p className="txt text-[13.5px] mt-1">{meeting.participants}</p></div>
                <div><p className="txt-muted text-[12px] font-semibold uppercase">Internal</p><p className="txt text-[13.5px] mt-1">{meeting.internalParticipants}</p></div>
              </div>
            </div>
          </div>

          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title="Agenda" />
            <div className="pt-2">
              <p className="txt text-[13.5px] whitespace-pre-wrap">{meeting.agenda}</p>
            </div>
          </div>

          {/* Related Records Widgets */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Related Records" />
              <div className="flex flex-col gap-4 pt-2">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-2)] text-[12px] font-bold text-[var(--accent)]">
                    <Target className="h-5 w-5" />
                  </div>
                  <div><p className="txt text-[14px] font-semibold">{meeting.opportunity}</p><p className="txt-faint text-[12px]">Opportunity</p></div>
                </div>
                <div className="flex items-center gap-3 border-t border-[var(--border)] pt-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-2)] text-[12px] font-bold text-[var(--accent)]">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div><p className="txt text-[14px] font-semibold">{meeting.account}</p><p className="txt-faint text-[12px]">Account</p></div>
                </div>
              </div>
            </div>
            
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title="Tasks & Follow-ups" action={<button className="flex items-center gap-1 text-[12px] font-semibold text-[var(--accent)] hover:opacity-80"><Plus className="h-3 w-3" /> Add Task</button>} />
              <div className="flex flex-col gap-3 pt-2">
                <div className="flex items-center gap-3">
                  <CheckSquare className="h-5 w-5 text-[var(--muted)]" />
                  <div><p className="txt text-[13px] font-semibold">Send implementation timeline</p><p className="txt-faint text-[11px]">Due Tomorrow</p></div>
                </div>
                <div className="flex items-center gap-3 border-t border-[var(--border)] pt-3">
                  <CheckSquare className="h-5 w-5 text-[var(--muted)]" />
                  <div><p className="txt text-[13px] font-semibold">Schedule tech review</p><p className="txt-faint text-[11px]">Due Friday</p></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      ),
    },
    { 
      id: 'timeline', 
      label: 'Timeline', 
      content: (
        <div className="surface bd rounded-2xl border p-5">
          <SectionHeader title="Meeting Timeline" />
          <div className="pt-2">
            {MOCK_ACTIVITIES.map((activity, i) => (
              <ActivityItem key={activity.id} activity={activity} showConnector={i < MOCK_ACTIVITIES.length - 1} />
            ))}
          </div>
        </div>
      ) 
    },
    { id: 'notes', label: 'Notes', content: <div className="p-4 text-[13px] txt-faint">No manual notes added. See AI Summary.</div> },
    { id: 'attachments', label: 'Attachments', content: <div className="p-4 text-[13px] txt-faint">No files attached.</div> },
  ];

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      
      {/* ── Page Header ── */}
      <div className="flex flex-col gap-4">
        <button onClick={() => router.push('/meetings')} className="txt-muted hover:txt flex w-fit items-center gap-1 text-[13px] font-medium transition-colors">
          <ArrowLeft className="h-4 w-4" /> Back to Meetings
        </button>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-sky-500 to-blue-600 shadow-sm">
              <CalendarIcon className="h-6 w-6 text-white" />
            </div>
            <div className="mt-1">
              <div className="flex items-center gap-3">
                <h1 className="font-display txt text-[24px] font-extrabold leading-tight tracking-tight">
                  {meeting.title}
                </h1>
                <StatusBadge label={meeting.status} variant={meeting.status === 'Completed' ? 'success' : 'accent'} />
              </div>
              <div className="txt-muted mt-1.5 flex items-center gap-2 text-[13px] font-medium">
                <span className="flex items-center gap-1"><Video className="h-4 w-4" /> {meeting.type}</span>
                <span className="border-l border-[var(--border)] pl-2 ml-1">{meeting.date} at {meeting.startTime}</span>
              </div>
            </div>
          </div>
          
          <div className="flex flex-wrap items-center gap-2">
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <CheckCircle2 className="h-4 w-4" /> Mark Complete
            </button>
            <button className="ctl flex items-center gap-2 px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80">
              <Mail className="h-4 w-4" /> Follow-up
            </button>
            <button
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:opacity-90 hover:shadow-md"
              style={{ background: 'var(--accent)' }}
            >
              <Sparkles className="h-4 w-4 text-violet-200" /> Gen. AI Summary
            </button>
          </div>
        </div>
      </div>

      {/* ── Content Area: Main + Sidebar ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        {/* Left: Main Tabs */}
        <div className="min-w-0">
           <Tabs tabs={tabs} defaultTab="overview" />
        </div>
        
        {/* Right: AI Panel Sidebar */}
        <div className="flex flex-col gap-6">
          <AIMeetingAssistant data={MOCK_AI_DATA} />
        </div>
      </div>
    </div>
  );
}
