'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Loader2, Mails, ShieldAlert, X } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import TablePagination from '@/components/crm/ai/shared/TablePagination';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { ListEmpty, ListError } from '@/components/crm/shared/ListStates';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useCollection } from '@/features/shared/hooks/useCollection';
import { formatTimestamp, toInstant } from '@/features/admin/audit-logs';
import {
  getEmailDeliverySummary,
  listEmailDeliveries,
  providerDelivers,
  providerLabel,
  statusVariantFor,
  templateLabel,
  type EmailDelivery,
  type EmailDeliveryStatus,
  type EmailDeliverySummary,
} from '@/features/admin/email-deliveries';

/* ============================================================
   ADMIN — EMAIL DELIVERIES

   What the product tried to send on this organization's behalf,
   and what happened to it. Rows come from
   `GET /api/v1/email-deliveries`, gated on `audit.VIEW` and
   scoped server-side to the caller's organization.

   The two questions this exists to answer are "did they get it?"
   and "why did they get two?", and both used to require reading
   application logs on the server.

   Password resets are deliberately absent. They are addressed to
   a person's global identity rather than to this organization,
   so they carry no tenant and the row-level policy keeps them
   out of every tenant's view — a reset is between the product
   and the account holder, and an organization's administrators
   are not a party to it.

   Every filter is a query parameter, never a client-side pass
   over the current page: filtering in the browser would leave
   the result count describing a different set than the table.
   ============================================================ */

const PAGE_SIZE_DEFAULT = 25;

const ANY_STATUS = { value: '', label: 'All outcomes' };
const ANY_TEMPLATE = { value: '', label: 'All message types' };

const STATUSES: EmailDeliveryStatus[] = ['SENT', 'PENDING', 'FAILED', 'SUPPRESSED'];

interface Filters {
  status: string;
  template: string;
  recipient: string;
  from: string;
  to: string;
}

const NO_FILTERS: Filters = { status: '', template: '', recipient: '', from: '', to: '' };

export default function AdminEmailDeliveriesPage() {
  const { can } = usePermissions();
  const mayView = can('audit', 'VIEW');

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_DEFAULT);
  const [selected, setSelected] = useState<EmailDelivery | null>(null);

  const [summary, setSummary] = useState<EmailDeliverySummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await getEmailDeliverySummary();
        if (!cancelled) {
          setSummary(loaded);
          setSummaryError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setSummaryError(describeApiError(caught, 'Could not load the delivery summary.'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayView]);

  const fetcher = useCallback(
    () =>
      listEmailDeliveries({
        page,
        page_size: pageSize,
        status: (filters.status || null) as EmailDeliveryStatus | null,
        template: filters.template || null,
        to_address: filters.recipient.trim() || null,
        sent_from: toInstant(filters.from),
        sent_to: toInstant(filters.to),
        sort_by: 'created_at',
        sort_dir: 'desc',
      }),
    [page, pageSize, filters],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<EmailDelivery>(
    fetcher,
    [
      page,
      pageSize,
      filters.status,
      filters.template,
      filters.recipient,
      filters.from,
      filters.to,
    ],
    { errorMessage: 'Could not load the delivery log.' },
  );

  const update = (patch: Partial<Filters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setPage(1);
  };

  const filtered = useMemo(
    () => Object.values(filters).some((value) => value !== ''),
    [filters],
  );

  // Read off the rows on screen rather than the summary: the summary counts
  // the whole log, and what an administrator needs to know is whether the
  // provider handling *these* messages actually sends anything.
  const undeliveringProvider = useMemo(() => {
    const found = items.find((row) => !providerDelivers(row.provider));
    return found?.provider ?? null;
  }, [items]);

  const columns: ColumnDef<EmailDelivery>[] = useMemo(
    () => [
      {
        key: 'created_at',
        label: 'Requested',
        minWidth: '9rem',
        render: (row) => {
          const { date, time } = formatTimestamp(row.created_at);
          return (
            <div>
              <p className="txt text-[12.5px] font-medium">{date}</p>
              <p className="txt-faint tabular-nums text-[11.5px]">{time}</p>
            </div>
          );
        },
      },
      {
        key: 'to_address',
        label: 'Recipient',
        minWidth: '13rem',
        render: (row) => (
          <span className="txt break-all text-[12.5px] font-medium">{row.to_address}</span>
        ),
      },
      {
        key: 'template',
        label: 'Message',
        minWidth: '11rem',
        render: (row) => (
          <div>
            <p className="txt text-[12.5px] font-medium">{templateLabel(row.template)}</p>
            <p className="txt-faint truncate text-[11.5px]">{row.subject}</p>
          </div>
        ),
      },
      {
        key: 'provider',
        label: 'Provider',
        minWidth: '8rem',
        hideBelow: 'lg',
        render: (row) => (
          <span className="txt-muted text-[12.5px]">{providerLabel(row.provider)}</span>
        ),
      },
      {
        key: 'status',
        label: 'Outcome',
        align: 'center',
        minWidth: '6rem',
        render: (row) => (
          <StatusBadge
            label={templateLabel(row.status)}
            variant={statusVariantFor(row.status)}
          />
        ),
      },
    ],
    [],
  );

  const header = (
    <div className="flex items-center gap-3.5">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-600 to-indigo-700">
        <Mails className="h-5 w-5 text-white" />
      </div>
      <div>
        <h1 className="font-display txt text-[22px] font-extrabold">Email Deliveries</h1>
        <p className="txt-muted mt-0.5 text-[13px]">
          What we sent on your behalf, and whether it arrived.
        </p>
      </div>
    </div>
  );

  // Permission is enforced by the API on every request; this only decides what
  // to render instead of a table the caller would receive a 403 from.
  if (!mayView) {
    return (
      <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
        {header}
        <div
          role="status"
          className="surface bd flex flex-col items-center gap-3 rounded-2xl border px-6 py-14 text-center"
        >
          <div
            className="flex h-11 w-11 items-center justify-center rounded-full"
            style={{ background: 'var(--surface-2)' }}
          >
            <ShieldAlert className="txt-faint h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="txt text-[14px] font-semibold">
              You do not have access to the delivery log
            </p>
            <p className="txt-muted mx-auto mt-1.5 max-w-lg text-[12.5px] leading-relaxed">
              The log names everyone this organization has emailed, so reading it
              is granted deliberately rather than by default. Ask an administrator
              if you need access.
            </p>
          </div>
          <p className="txt-faint mt-1 text-[11.5px] font-medium">
            Requires:{' '}
            <span className="bd rounded-md border px-1.5 py-0.5 font-mono text-[11px]">
              audit.VIEW
            </span>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 lg:p-8">
      {header}

      {/* ---- The one thing worth interrupting for ----
          A green "Sent" against a provider that discards everything would let
          an administrator conclude their invitations arrived. Say so plainly. */}
      {undeliveringProvider !== null && (
        <div
          role="status"
          className="bd flex items-start gap-3 rounded-2xl border p-4"
          style={{ background: 'var(--surface-2)' }}
        >
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"
            aria-hidden="true"
          />
          <p className="txt-muted text-[12.5px] leading-relaxed">
            <span className="txt font-semibold">No mail is leaving this deployment.</span>{' '}
            The email provider is set to{' '}
            <span className="font-mono text-[11.5px]">{undeliveringProvider}</span>, which
            records a delivery without sending one. Messages marked “Sent” below
            reached the provider, not the recipient. Configure Microsoft Graph to change that.
          </p>
        </div>
      )}

      {/* ---- Counts ---- */}
      {summary !== null && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {STATUSES.map((state) => (
            <button
              key={state}
              type="button"
              onClick={() => update({ status: filters.status === state ? '' : state })}
              aria-pressed={filters.status === state}
              className="surface bd rounded-2xl border p-3.5 text-left transition hover:opacity-90"
              style={
                filters.status === state
                  ? { borderColor: 'var(--accent)' }
                  : undefined
              }
            >
              <p className="txt-faint text-[11px] font-bold uppercase tracking-wider">
                {templateLabel(state)}
              </p>
              <p className="txt mt-1 tabular-nums text-[20px] font-extrabold">
                {summary.counts[state] ?? 0}
              </p>
            </button>
          ))}
        </div>
      )}

      {/* ---- Filters ---- */}
      <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">
              Message type
            </span>
            <FilterSelect
              value={filters.template}
              onChange={(event) => update({ template: event.target.value })}
              options={[
                ANY_TEMPLATE,
                ...(summary?.templates ?? []).map((value) => ({
                  value,
                  label: templateLabel(value),
                })),
              ]}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">
              Outcome
            </span>
            <FilterSelect
              value={filters.status}
              onChange={(event) => update({ status: event.target.value })}
              options={[
                ANY_STATUS,
                ...STATUSES.map((value) => ({ value, label: templateLabel(value) })),
              ]}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">
              Recipient
            </span>
            <input
              type="search"
              value={filters.recipient}
              onChange={(event) => update({ recipient: event.target.value })}
              placeholder="Part of an address"
              className="ctl px-3 py-2 text-[13px] outline-none transition-colors focus:border-[var(--accent)]"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">
              From
            </span>
            <input
              type="datetime-local"
              value={filters.from}
              onChange={(event) => update({ from: event.target.value })}
              className="ctl px-3 py-2 text-[13px] outline-none transition-colors focus:border-[var(--accent)]"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">
              To
            </span>
            <input
              type="datetime-local"
              value={filters.to}
              onChange={(event) => update({ to: event.target.value })}
              className="ctl px-3 py-2 text-[13px] outline-none transition-colors focus:border-[var(--accent)]"
            />
          </label>

          {filtered && (
            <button
              type="button"
              onClick={() => {
                setFilters(NO_FILTERS);
                setPage(1);
              }}
              className="ctl bd inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" /> Clear
            </button>
          )}

          {refreshing && (
            <Loader2
              className="txt-faint mb-2 h-4 w-4 motion-safe:animate-spin"
              aria-label="Refreshing"
            />
          )}
        </div>

        <p className="txt-faint text-[11.5px]">
          Message contents are not stored — only who it went to and which message
          it was. Password resets are not listed here: they are sent to a person’s
          account rather than to this organization.
        </p>
        {summaryError !== null && <p className="txt-faint text-[11.5px]">{summaryError}</p>}
      </div>

      {/* ---- Table ---- */}
      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : (
        <div className="surface bd overflow-hidden rounded-2xl border">
          <DataTable
            columns={columns}
            data={items}
            rowKey={(row) => row.id}
            onRowClick={(row) => setSelected(row)}
            loading={status === 'loading'}
            skeletonRows={8}
            emptyState={
              <ListEmpty
                title={filtered ? 'No messages match those filters' : 'Nothing sent yet'}
                hint={
                  filtered
                    ? 'Widen the date range, or clear the filters to see everything.'
                    : 'Invitations and meeting reminders appear here as they are sent.'
                }
              />
            }
          />
          {pagination !== null && pagination.total > 0 && (
            <TablePagination
              page={page}
              pageSize={pageSize}
              totalItems={pagination.total}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          )}
        </div>
      )}

      {/* ---- Detail ---- */}
      <SlideDrawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected ? templateLabel(selected.template) : ''}
        subtitle={selected ? selected.to_address : undefined}
        width="max-w-lg"
      >
        {selected !== null && <DeliveryDetail delivery={selected} />}
      </SlideDrawer>
    </div>
  );
}

function DeliveryDetail({ delivery }: { delivery: EmailDelivery }) {
  const requested = formatTimestamp(delivery.created_at);
  const sent = delivery.sent_at === null ? null : formatTimestamp(delivery.sent_at);

  return (
    <div className="space-y-5 p-5">
      <div className="flex items-center gap-2">
        <StatusBadge
          label={templateLabel(delivery.status)}
          variant={statusVariantFor(delivery.status)}
        />
        <span className="txt-faint text-[12px]">via {providerLabel(delivery.provider)}</span>
      </div>

      <Field label="Subject" value={delivery.subject} />
      <Field label="Recipient" value={delivery.to_address} />
      <Field label="Requested" value={`${requested.date} ${requested.time}`} />
      <Field
        label="Sent"
        value={sent === null ? 'Not yet' : `${sent.date} ${sent.time}`}
      />
      <Field
        label="Provider reference"
        value={delivery.provider_message_id ?? '—'}
        mono
      />

      {delivery.error !== null && (
        <div>
          <p className="txt-faint text-[11px] font-bold uppercase tracking-wider">
            Failure
          </p>
          <p className="mt-1 break-words rounded-lg p-3 font-mono text-[11.5px] leading-relaxed text-red-500"
            style={{ background: 'var(--surface-2)' }}
          >
            {delivery.error}
          </p>
        </div>
      )}

      <p className="txt-faint text-[11.5px] leading-relaxed">
        The message itself is not stored. Keeping a copy would put invitation and
        password-reset links — which are credentials — somewhere administrators
        could read them.
      </p>
    </div>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="txt-faint text-[11px] font-bold uppercase tracking-wider">{label}</p>
      <p
        className={`txt mt-1 break-all text-[13px] ${mono ? 'font-mono text-[11.5px]' : ''}`}
      >
        {value}
      </p>
    </div>
  );
}
