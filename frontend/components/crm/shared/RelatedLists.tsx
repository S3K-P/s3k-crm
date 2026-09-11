'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Loader2, Plus, Star } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { type Account } from '@/features/crm/accounts';
import { listContacts, makeContactPrimary, type Contact } from '@/features/crm/contacts';
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

const MAX_ROWS = 50;

function PanelShell({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="surface bd rounded-2xl border p-5">
      <div className="flex items-center justify-between gap-3">
        <SectionHeader title={title} />
        {action}
      </div>
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

export function AccountContactsPanel({
  account,
  onPrimaryChanged,
}: {
  account: Account;
  /** Bumped after a promotion, so the summary header's figure stays in sync. */
  onPrimaryChanged?: () => void;
}) {
  const router = useRouter();
  const { can } = usePermissions();
  const mayView = can('contacts', 'VIEW');
  const mayCreate = can('contacts', 'CREATE');
  const mayEdit = can('contacts', 'EDIT');

  const [items, setItems] = useState<Contact[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  // Set directly in the click handler below, not synced from a prop via an
  // effect: the account object itself is refreshed by `onPrimaryChanged`
  // (the parent's `reload()`), and this only bridges the moment before that
  // refetch lands so the star badge does not wait on a second round trip.
  const [optimisticPrimaryId, setOptimisticPrimaryId] = useState<string | null>(null);
  const primaryContactId = optimisticPrimaryId ?? account.primary_contact_id;
  const [promotingId, setPromotingId] = useState<string | null>(null);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;
    void (async () => {
      try {
        const page = await listContacts({
          account_id: account.id,
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
  }, [account.id, mayView]);

  if (!mayView) return null;

  const handleMakePrimary = async (contact: Contact) => {
    setPromotingId(contact.id);
    try {
      await makeContactPrimary(contact.id);
      // Reflected at once rather than waiting for a reload: the backend
      // demotes the incumbent in the same transaction, so this is already
      // the true state.
      setOptimisticPrimaryId(contact.id);
      notifySuccess('Primary contact updated', `${contact.full_name} is now primary.`);
      onPrimaryChanged?.();
    } catch (caught) {
      notifyError(caught, 'Could not make this contact primary.');
    } finally {
      setPromotingId(null);
    }
  };

  const columns: ColumnDef<Contact>[] = [
    {
      key: 'name',
      label: 'Name',
      minWidth: '160px',
      render: (row) => (
        <span className="txt font-semibold">
          {row.full_name}
          {row.id === primaryContactId && (
            <Star
              className="ml-1.5 inline h-3.5 w-3.5 align-text-top text-amber-500"
              fill="currentColor"
              aria-label="Primary contact"
            />
          )}
        </span>
      ),
    },
    {
      key: 'job_title',
      label: 'Role',
      hideBelow: 'sm',
      render: (row) => row.job_title ?? <span className="txt-faint">—</span>,
    },
    {
      key: 'email',
      label: 'Email',
      hideBelow: 'md',
      render: (row) => row.email ?? <span className="txt-faint">—</span>,
    },
    {
      key: 'status',
      label: 'Status',
      render: (row) => <StatusBadge label={humanize(row.status)} variant={statusVariant(row.status)} />,
    },
    {
      key: 'actions',
      label: '',
      align: 'right',
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          {mayEdit && row.id !== primaryContactId && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                void handleMakePrimary(row);
              }}
              disabled={promotingId === row.id}
              className="ctl bd rounded-lg border px-2.5 py-1 text-[11.5px] font-semibold transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {promotingId === row.id ? 'Saving…' : 'Make primary'}
            </button>
          )}
          <ArrowRight className="txt-faint h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        </div>
      ),
    },
  ];

  return (
    <PanelShell
      title={total > 0 ? `Contacts (${total})` : 'Contacts'}
      action={
        mayCreate && (
          <button
            type="button"
            onClick={() => router.push(`/contacts?account_id=${account.id}`)}
            className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] font-semibold transition hover:opacity-80"
          >
            <Plus className="h-3 w-3" /> Add contact
          </button>
        )
      }
    >
      {error !== null ? (
        <p className="text-[12.5px] text-red-500">{error}</p>
      ) : (
        <DataTable
          columns={columns}
          data={items ?? []}
          rowKey={(row) => row.id}
          onRowClick={(row) => router.push(`/contacts/${row.id}`)}
          loading={items === null}
          skeletonRows={3}
          emptyState={
            <p className="txt-faint py-4 text-center text-[12.5px]">
              No contacts are linked to this account yet.
            </p>
          }
        />
      )}
    </PanelShell>
  );
}

export function AccountOpportunitiesPanel({ accountId }: { accountId: string }) {
  const router = useRouter();
  const { can } = usePermissions();
  const mayView = can('opportunities', 'VIEW');
  const mayCreate = can('opportunities', 'CREATE');

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

  const formatMoney = (opportunity: Opportunity): string =>
    opportunity.deal_value
      ? Number(opportunity.deal_value).toLocaleString(undefined, {
          style: 'currency',
          currency: opportunity.currency,
          maximumFractionDigits: 0,
        })
      : '—';

  const columns: ColumnDef<Opportunity>[] = [
    {
      key: 'name',
      label: 'Deal',
      minWidth: '160px',
      render: (row) => (
        <span className={`font-semibold ${isClosed(row) ? 'txt-faint' : 'txt'}`}>{row.name}</span>
      ),
    },
    {
      key: 'deal_value',
      label: 'Amount',
      align: 'right',
      render: (row) => <span className="tabular-nums">{formatMoney(row)}</span>,
    },
    {
      key: 'stage_id',
      label: 'Stage',
      render: (row) => (
        <StatusBadge
          label={stageName(row.stage_id)}
          variant={row.won_at ? 'success' : row.lost_at ? 'danger' : 'accent'}
        />
      ),
    },
    {
      key: 'actions',
      label: '',
      align: 'right',
      render: () => <ArrowRight className="txt-faint h-3.5 w-3.5 shrink-0" aria-hidden="true" />,
    },
  ];

  return (
    <PanelShell
      title={total > 0 ? `Deals (${total})` : 'Deals'}
      action={
        mayCreate && (
          <button
            type="button"
            onClick={() => router.push(`/opportunities?account_id=${accountId}`)}
            className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] font-semibold transition hover:opacity-80"
          >
            <Plus className="h-3 w-3" /> New deal
          </button>
        )
      }
    >
      {error !== null ? (
        <p className="text-[12.5px] text-red-500">{error}</p>
      ) : (
        <DataTable
          columns={columns}
          data={items ?? []}
          rowKey={(row) => row.id}
          onRowClick={(row) => router.push(`/opportunities/${row.id}`)}
          loading={items === null}
          skeletonRows={3}
          emptyState={
            <p className="txt-faint py-4 text-center text-[12.5px]">
              No deals have been raised against this account yet.
            </p>
          }
        />
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
