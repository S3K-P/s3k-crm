'use client';

import { Info } from 'lucide-react';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import CopyButton from '@/components/crm/ai/shared/CopyButton';
import { emailToText } from './nba-helpers';
import type { NbaDetail, NbaRecord } from '@/features/ai/next-best-action/types';

/* ============================================================
   NBA MESSAGE SHEET
   Preview for a locally generated email or WhatsApp message.
   Reuses the CRM's SlideDrawer. Nothing is ever sent — the
   only outbound action available is copy to clipboard.
   ============================================================ */

export type MessageKind = 'email' | 'whatsapp';

interface NbaMessageSheetProps {
  open: boolean;
  kind: MessageKind;
  record: NbaRecord | null;
  detail: NbaDetail | null;
  onClose: () => void;
}

export default function NbaMessageSheet({
  open,
  kind,
  record,
  detail,
  onClose,
}: NbaMessageSheetProps) {
  if (!record || !detail) return null;

  const isEmail = kind === 'email';
  const copyValue = isEmail ? emailToText(detail.suggestedEmail) : detail.suggestedWhatsapp;

  return (
    <SlideDrawer
      open={open}
      onClose={onClose}
      title={isEmail ? 'Suggested Email' : 'Suggested WhatsApp Message'}
      subtitle={`${record.leadName} · ${record.company}`}
      width="max-w-xl"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80"
          >
            Close
          </button>
          <CopyButton
            value={copyValue}
            label={isEmail ? 'Email draft' : 'WhatsApp message'}
            showLabel
            className="px-5 py-2.5 text-[13px]"
          />
        </>
      }
    >
      <div className="space-y-4">
        {/* Recipient context */}
        <dl className="surface-2 bd grid gap-3 rounded-xl border p-3.5 sm:grid-cols-2">
          <div>
            <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">To</dt>
            <dd className="txt mt-0.5 text-[13px] font-medium">{record.leadName}</dd>
          </div>
          <div>
            <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">
              {isEmail ? 'Email' : 'Phone'}
            </dt>
            <dd className="txt mt-0.5 break-all text-[13px] font-medium">
              {isEmail ? record.email : record.phone}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Opportunity</dt>
            <dd className="txt mt-0.5 text-[13px] font-medium">{record.opportunity}</dd>
          </div>
        </dl>

        {/* Message */}
        {isEmail ? (
          <div className="surface-2 bd rounded-xl border p-4">
            <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">Subject</p>
            <p className="txt mt-0.5 text-[13.5px] font-semibold">{detail.suggestedEmail.subject}</p>
            <div className="bd mt-3 border-t pt-3">
              <p className="txt-muted whitespace-pre-line text-[13px] leading-relaxed">
                {detail.suggestedEmail.body}
              </p>
            </div>
          </div>
        ) : (
          <div className="surface-2 bd rounded-xl border p-4">
            <p className="txt-faint mb-2 text-[10.5px] font-bold uppercase tracking-wider">Message</p>
            <p className="txt whitespace-pre-line rounded-xl px-3.5 py-3 text-[13px] leading-relaxed"
              style={{ background: 'var(--accent-soft)' }}
            >
              {detail.suggestedWhatsapp}
            </p>
            <p className="txt-faint mt-2 text-[11.5px]">
              {detail.suggestedWhatsapp.length} characters
            </p>
          </div>
        )}

        <p className="txt-muted flex items-start gap-2 text-[12px] leading-relaxed">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: 'var(--accent)' }} aria-hidden="true" />
          Draft only. This screen does not connect to an email or messaging service — copy the text to
          send it from your usual client.
        </p>
      </div>
    </SlideDrawer>
  );
}
