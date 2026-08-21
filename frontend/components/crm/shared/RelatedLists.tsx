'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Loader2 } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { listContacts, type Contact } from '@/features/crm/contacts';
import {
  isClosed,
  listOpportunities,
  listStages,
  type Opportunity,
  type PipelineStage,
} from '@/features/crm/opportunities';

/* ============================================================
   RELATED LISTS

   The child records an account owns.

   `crm.contacts.account_id` and `crm.opportunities.account_id`
   are real foreign keys, and both list endpoints accept an
   `account_id` filter — so this data was always reachable. The
   account detail page simply never asked for it, which left the
   Account -> Contacts and Account -> Opportunities relationships
   navigable in one direction only.

   Both panels return `null` when the caller lacks read
   permission, rather than rendering an empty box that implies
   the account has no contacts.
   ============================================================ */

const MAX_ROWS = 10;

function PanelShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="surface bd rounded-2xl border p-5">
      <SectionHeader title={title} />
      <div className="pt-2">{children}</div>
    </div>
  );
}

function Loading() {
  return (
    <p className="txt-muted flex items-center gap-2 py-4 text-[12.5px]">
      <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" /> Loading…
    </p>
  );
}

export function AccountContactsPanel({ accountId }: { accountId: string }) {
  const router = useRouter();
  const { can } = usePermissions();
  const mayView = can('contacts', 'VIEW');

  const [items, setItems] = useState<Contact[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;
    void (async () => {
      try {
        const page = await listContacts({
          account_id: accountId,
          page_size: MAX_ROWS,
          sort_by: 'last_name',
          sort_dir: 'asc',
        });
        if (!cancelled) {
          setItems(page.data);
          setTotal(page.pagination.total);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load contacts.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accountId, mayView]);

  if (!mayView) return null;

  return (
    <PanelShell title={total > 0 ? `Contacts (${total})` : 'Contacts'}>
      {error !== null ? (
        <p className="text-[12.5px] text-red-500">{error}</p>
      ) : items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <p className="txt-faint py-4 text-center text-[12.5px]">
          No contacts are linked to this account yet.
        </p>
      ) : (
        <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {items.map((contact) => (
            <li key={contact.id}>
              <button
                type="button"
                onClick={() => router.push(`/contacts/${contact.id}`)}
                className="flex w-full items-center gap-3 py-2.5 text-left transition hover:opacity-70"
              >
                <div className="min-w-0 flex-1">
                  <p className="txt truncate text-[13px] font-semibold">{contact.full_name}</p>
                  <p className="txt-faint truncate text-[11.5px]">
                    {contact.job_title ?? contact.email ?? 'No title recorded'}
                  </p>
                </div>
                <StatusBadge
                  label={humanize(contact.status)}
                  variant={statusVariant(contact.status)}
                />
                <ArrowRight className="txt-faint h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {total > MAX_ROWS && (
        <button
          type="button"
          onClick={() => router.push('/contacts')}
          className="mt-3 text-[12.5px] font-semibold hover:underline"
          style={{ color: 'var(--accent)' }}
        >
          View all {total} contacts
        </button>
      )}
    </PanelShell>
  );
}

export function AccountOpportunitiesPanel({ accountId }: { accountId: string }) {
  const router = useRouter();
  const { can } = usePermissions();
  const mayView = can('opportunities', 'VIEW');

  const [items, setItems] = useState<Opportunity[] | null>(null);
  const [total, setTotal] = useState(0);
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;
    void (async () => {
      try {
        const [page, loadedStages] = await Promise.all([
          listOpportunities({
            account_id: accountId,
            page_size: MAX_ROWS,
            sort_by: 'created_at',
            sort_dir: 'desc',
          }),
          listStages().catch(() => [] as PipelineStage[]),
        ]);
        if (!cancelled) {
          setItems(page.data);
          setTotal(page.pagination.total);
          setStages(loadedStages);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load opportunities.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accountId, mayView]);

  if (!mayView) return null;

  const stageName = (stageId: string): string =>
    stages.find((stage) => stage.id === stageId)?.name ?? 'Unknown stage';

  const openValue = (items ?? [])
    .filter((opportunity) => !isClosed(opportunity))
    .reduce((sum, opportunity) => sum + Number(opportunity.deal_value ?? 0), 0);

  return (
    <PanelShell title={total > 0 ? `Opportunities (${total})` : 'Opportunities'}>
      {error !== null ? (
        <p className="text-[12.5px] text-red-500">{error}</p>
      ) : items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <p className="txt-faint py-4 text-center text-[12.5px]">
          No opportunities have been raised against this account yet.
        </p>
      ) : (
        <>
          {openValue > 0 && (
            <p className="txt-muted mb-2 text-[12px]">
              Open pipeline on this page:{' '}
              <span className="txt font-semibold tabular-nums">
                {openValue.toLocaleString(undefined, {
                  style: 'currency',
                  currency: items[0]?.currency ?? 'USD',
                  maximumFractionDigits: 0,
                })}
              </span>
            </p>
          )}
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {items.map((opportunity) => (
              <li key={opportunity.id}>
                <button
                  type="button"
                  onClick={() => router.push(`/opportunities/${opportunity.id}`)}
                  className="flex w-full items-center gap-3 py-2.5 text-left transition hover:opacity-70"
                >
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate text-[13px] font-semibold ${
                        isClosed(opportunity) ? 'txt-faint' : 'txt'
                      }`}
                    >
                      {opportunity.name}
                    </p>
                    <p className="txt-faint truncate text-[11.5px]">
                      {stageName(opportunity.stage_id)}
                      {opportunity.expected_close_date
                        ? ` · closes ${opportunity.expected_close_date}`
                        : ''}
                    </p>
                  </div>
                  <span className="txt shrink-0 text-[12.5px] font-semibold tabular-nums">
                    {opportunity.deal_value
                      ? Number(opportunity.deal_value).toLocaleString(undefined, {
                          style: 'currency',
                          currency: opportunity.currency,
                          maximumFractionDigits: 0,
                        })
                      : '—'}
                  </span>
                  <ArrowRight className="txt-faint h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {total > MAX_ROWS && (
        <button
          type="button"
          onClick={() => router.push('/opportunities')}
          className="mt-3 text-[12.5px] font-semibold hover:underline"
          style={{ color: 'var(--accent)' }}
        >
          View all {total} opportunities
        </button>
      )}
    </PanelShell>
  );
}

export function ContactOpportunitiesPanel({ contactId }: { contactId: string }) {
  const router = useRouter();
  const { can } = usePermissions();
  const mayView = can('opportunities', 'VIEW');

  const [items, setItems] = useState<Opportunity[] | null>(null);
  const [total, setTotal] = useState(0);
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;
    void (async () => {
      try {
        const [page, loadedStages] = await Promise.all([
          listOpportunities({
            primary_contact_id: contactId,
            page_size: MAX_ROWS,
            sort_by: 'created_at',
            sort_dir: 'desc',
          }),
          listStages().catch(() => [] as PipelineStage[]),
        ]);
        if (!cancelled) {
          setItems(page.data);
          setTotal(page.pagination.total);
          setStages(loadedStages);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(describeApiError(caught, 'Could not load opportunities.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [contactId, mayView]);

  if (!mayView) return null;

  const stageName = (stageId: string): string =>
    stages.find((stage) => stage.id === stageId)?.name ?? 'Unknown stage';

  return (
    <PanelShell title={total > 0 ? `Opportunities (${total})` : 'Opportunities'}>
      {error !== null ? (
        <p className="text-[12.5px] text-red-500">{error}</p>
      ) : items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <p className="txt-faint py-4 text-center text-[12.5px]">
          No opportunities linked to this contact yet.
        </p>
      ) : (
        <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {items.map((opportunity) => (
            <li key={opportunity.id}>
              <button
                type="button"
                onClick={() => router.push(`/opportunities/${opportunity.id}`)}
                className="flex w-full items-center gap-3 py-2.5 text-left transition hover:opacity-70"
              >
                <div className="min-w-0 flex-1">
                  <p
                    className={`truncate text-[13px] font-semibold ${
                      isClosed(opportunity) ? 'txt-faint' : 'txt'
                    }`}
                  >
                    {opportunity.name}
                  </p>
                  <p className="txt-faint truncate text-[11.5px]">
                    {stageName(opportunity.stage_id)}
                  </p>
                </div>
                <span className="txt shrink-0 text-[12.5px] font-semibold tabular-nums">
                  {opportunity.deal_value
                    ? Number(opportunity.deal_value).toLocaleString(undefined, {
                        style: 'currency',
                        currency: opportunity.currency,
                        maximumFractionDigits: 0,
                      })
                    : '—'}
                </span>
                <ArrowRight className="txt-faint h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </PanelShell>
  );
}
