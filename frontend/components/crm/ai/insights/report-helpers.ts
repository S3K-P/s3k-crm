import {
  ArrowRightLeft,
  CheckSquare,
  FileSignature,
  FileText,
  Mail,
  Phone,
  Users,
  type LucideIcon,
} from 'lucide-react';
import type { BadgeVariant } from '@/components/crm/shared/StatusBadge';
import type {
  AgendaItem,
  CallScriptSection,
  EmailDraft,
  NbaPriority,
  RiskSeverity,
} from '@/features/ai/next-best-action/types';
import type { ActivityRecord, SignalStrength } from '@/features/ai/insights/types';

/* ============================================================
   REPORT HELPERS
   Presentation mappings and plain-text serialisers used by the
   AI Insights report. Kept out of the component so the render
   tree stays readable.
   ============================================================ */

/* ---- Badge mappings ---- */

export const PRIORITY_VARIANT: Record<NbaPriority, BadgeVariant> = {
  Critical: 'danger',
  High: 'warning',
  Medium: 'accent',
  Low: 'neutral',
};

export const SEVERITY_VARIANT: Record<RiskSeverity, BadgeVariant> = {
  Critical: 'danger',
  High: 'danger',
  Medium: 'warning',
  Low: 'neutral',
};

export const STRENGTH_VARIANT: Record<SignalStrength, BadgeVariant> = {
  Strong: 'success',
  Moderate: 'accent',
  Emerging: 'neutral',
};

/* ---- Activity icon mapping (reuses the dashboard's gradient set) ---- */

export const ACTIVITY_ICONS: Record<
  ActivityRecord['type'],
  { icon: LucideIcon; gradient: string }
> = {
  call: { icon: Phone, gradient: 'from-emerald-500 to-green-600' },
  email: { icon: Mail, gradient: 'from-sky-500 to-blue-600' },
  meeting: { icon: Users, gradient: 'from-violet-600 to-indigo-600' },
  proposal: { icon: FileSignature, gradient: 'from-amber-500 to-orange-500' },
  stage: { icon: ArrowRightLeft, gradient: 'from-pink-500 to-rose-500' },
  document: { icon: FileText, gradient: 'from-sky-500 to-blue-600' },
  task: { icon: CheckSquare, gradient: 'from-emerald-500 to-green-600' },
};

/* ---- Plain-text serialisers for the Copy actions ---- */

export function emailToText(email: EmailDraft): string {
  return `Subject: ${email.subject}\n\n${email.body}`;
}

export function callScriptToText(sections: CallScriptSection[]): string {
  return sections
    .map(section => `${section.label.toUpperCase()}\n${section.lines.map(line => `  ${line}`).join('\n')}`)
    .join('\n\n');
}

export function agendaToText(items: AgendaItem[]): string {
  const total = items.reduce((sum, item) => sum + item.minutes, 0);
  const body = items
    .map(
      (item, index) =>
        `${index + 1}. ${item.topic} — ${item.minutes} min\n   Objective: ${item.objective}\n   Participants: ${item.participants}`,
    )
    .join('\n');
  return `Suggested meeting agenda (${total} minutes)\n\n${body}`;
}

export function takeawaysToText(subject: string, takeaways: string[]): string {
  return `${subject} — key takeaways\n\n${takeaways.map(item => `• ${item}`).join('\n')}`;
}
