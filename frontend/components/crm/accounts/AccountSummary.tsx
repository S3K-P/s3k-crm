'use client';

import { useEffect, useState } from 'react';
import { CalendarClock, CheckSquare, DollarSign, TrendingUp, User, Users } from 'lucide-react';

import KpiCard from '@/components/crm/cards/KpiCard';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { getAccountOverview, type AccountOverview } from '@/features/crm/accounts';

/* ============================================================
   ACCOUNT SUMMARY

   The Account 360 header: real aggregates from
   `GET /crm/accounts/{id}/overview` — never sample data, and
   never a bigger number than the caller's own contact/deal lists
   would show them (the backend narrows every count to what this
   caller may see).
   ============================================================ */

function money(value: string, currency: string | null): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return '—';
  if (currency === null) return amount.toLocaleString();
  try {
    return amount.toLocaleString(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    });
  } catch {
    return `${currency} ${amount.toLocaleString()}`;
  }
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function AccountSummary({
  accountId,
  refreshToken = 0,
}: {
  accountId: string;
  /** Bump this to force a re-fetch — e.g. after a contact is promoted to primary. */
  refreshToken?: number;
}) {
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await getAccountOverview(accountId);
        if (!cancelled) {
          setOverview(result);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load the account summary.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accountId, refreshToken]);

  if (error !== null) {
    return <p className="text-[12.5px] text-red-500">{error}</p>;
  }

  if (overview === null) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={index}
            className="surface bd h-[92px] animate-pulse rounded-2xl border"
            aria-hidden="true"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <KpiCard
        label="Open pipeline"
        value={money(overview.open_pipeline_value, overview.open_pipeline_currency)}
        delta={`${overview.open_deals_count} open deal${overview.open_deals_count === 1 ? '' : 's'}`}
        icon={TrendingUp}
        iconGradient="from-sky-500 to-blue-600"
      />
      <KpiCard
        label="Won revenue"
        value={money(overview.won_revenue, overview.won_revenue_currency)}
        delta={`${overview.won_deals_count} won deal${overview.won_deals_count === 1 ? '' : 's'}`}
        trend={overview.won_deals_count > 0 ? 'up' : 'flat'}
        icon={DollarSign}
        iconGradient="from-emerald-500 to-teal-600"
      />
      <KpiCard
        label="Contacts"
        value={String(overview.contacts_count)}
        icon={Users}
        iconGradient="from-violet-600 to-indigo-600"
      />
      <KpiCard
        label="Open tasks"
        value={String(overview.open_tasks_count)}
        icon={CheckSquare}
        iconGradient="from-amber-500 to-orange-500"
      />
      <KpiCard
        label="Owner"
        value={overview.owner_name ?? 'Unassigned'}
        icon={User}
        iconGradient="from-rose-500 to-pink-600"
      />
      <KpiCard
        label="Primary contact"
        value={overview.primary_contact_name ?? 'None set'}
        delta={overview.primary_contact_title ?? undefined}
        icon={User}
        iconGradient="from-fuchsia-500 to-purple-600"
      />
      <KpiCard
        label="Next meeting"
        value={overview.next_meeting_title ?? 'None scheduled'}
        delta={overview.next_meeting_at ? formatWhen(overview.next_meeting_at) : undefined}
        icon={CalendarClock}
        iconGradient="from-cyan-500 to-sky-600"
      />
    </div>
  );
}
