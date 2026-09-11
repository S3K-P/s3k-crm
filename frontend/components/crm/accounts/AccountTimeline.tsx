'use client';

import RecordTimeline from '@/components/crm/shared/RecordTimeline';
import { getAccountTimeline } from '@/features/crm/accounts';

/* ============================================================
   ACCOUNT TIMELINE

   Every event this caller may see against this account, merged
   and newest first: logged activities, deals created, stage
   moves, contacts added, tasks created and completed, sent
   email, and notes. Each of the last three is read through its
   owning module's own authorization (private notes, another
   user's drafts) rather than a copy of it — see
   `backend/app/products/crm/shared/timeline.py`.

   A thin wrapper around the record-type-agnostic `RecordTimeline`,
   which Contact and Opportunity also use against their own
   `/timeline` endpoint.
   ============================================================ */

export default function AccountTimeline({ accountId }: { accountId: string }) {
  return (
    <RecordTimeline
      dependencyKey={accountId}
      fetchEntries={(limit) => getAccountTimeline(accountId, limit)}
      emptyMessage="Nothing has happened on this account yet. Activity, deals, contacts, tasks, email and notes will appear here as they are recorded."
    />
  );
}
