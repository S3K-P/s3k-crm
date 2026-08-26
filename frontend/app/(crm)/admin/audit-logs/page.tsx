'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, ScrollText, ShieldAlert, X } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import TablePagination from '@/components/crm/ai/shared/TablePagination';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import SectionHeader from '@/components/crm/shared/SectionHeader';
import { ListEmpty, ListError } from '@/components/crm/shared/ListStates';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useCollection } from '@/features/shared/hooks/useCollection';
import {
  actionLabel,
  formatTimestamp,
  getAuditFilterOptions,
  isSecurityAction,
  listAuditLogs,
  statusVariantFor,
  summariseDetails,
  toInstant,
  type AuditFilterOptions,
  type AuditLogEntry,
  type AuditStatus,
} from '@/features/admin/audit-logs';

/* ============================================================
   ADMIN — AUDIT LOGS

   Rows come from `GET /api/v1/audit-logs`, gated on `audit.VIEW`
   and scoped server-side to the caller's organization. There is
   no organization parameter to send and none is sent: the
   backend reads the tenant from the verified request context,
   and PostgreSQL row-level security filters again underneath.

   This screen previously rendered five fabricated entries,
   including a failed sign-in from a specific IP address. An
   administrator reading that could reasonably have concluded
   the system was recording security events while nothing at all
   was being recorded. Everything here is now a real record of
   something that actually happened.

   Read-only, deliberately. There is no write route to call, and
   `platform.audit_logs` rejects UPDATE and DELETE at the
   database level for every role — so there is no edit control
   here to be disappointed by.

   Every filter is a query parameter, never a client-side pass
   over the current page: filtering in the browser would leave
   the result count describing a different set than the table.
   ============================================================ */

const PAGE_SIZE_DEFAULT = 25;

const ANY_ACTION = { value: '', label: 'All actions' };
const ANY_STATUS = { value: '', label: 'All outcomes' };
const ANY_ENTITY = { value: '', label: 'All record types' };

interface Filters {
  action: string;
  status: string;
  entityType: string;
  from: string;
  to: string;
}

const NO_FILTERS: Filters = { action: '', status: '', entityType: '', from: '', to: '' };

export default function AdminAuditLogsPage() {
  const { can } = usePermissions();
  const mayView = can('audit', 'VIEW');

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_DEFAULT);
  const [selected, setSelected] = useState<AuditLogEntry | null>(null);

  const [options, setOptions] = useState<AuditFilterOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  // The dropdowns are populated from this organization's own trail, so they
  // never offer a choice that can only return an empty table.
  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await getAuditFilterOptions();
        if (!cancelled) {
          setOptions(loaded);
          setOptionsError(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setOptionsError(describeApiError(caught, 'Could not load the filter options.'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayView]);

  const fetcher = useCallback(
    () =>
      listAuditLogs({
        page,
        page_size: pageSize,
        action: filters.action || null,
        status: (filters.status || null) as AuditStatus | null,
        entity_type: filters.entityType || null,
        occurred_from: toInstant(filters.from),
        occurred_to: toInstant(filters.to),
        sort_by: 'created_at',
        sort_dir: 'desc',
      }),
    [page, pageSize, filters],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<AuditLogEntry>(
    fetcher,
    [page, pageSize, filters.action, filters.status, filters.entityType, filters.from, filters.to],
    { errorMessage: 'Could not load the audit trail.' },
  );

  const update = (patch: Partial<Filters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setPage(1);
  };

  const filtered = useMemo(
    () => Object.values(filters).some((value) => value !== ''),
    [filters],
  );

  const columns: ColumnDef<AuditLogEntry>[] = useMemo(
    () => [
      {
        key: 'created_at',
        label: 'When',
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
        key: 'actor',
        label: 'Who',
        minWidth: '11rem',
        render: (row) => (
          <div>
            <p className="txt text-[12.5px] font-medium">
              {row.actor_name ?? row.actor_email ?? 'System'}
            </p>
            {row.actor_name !== null && row.actor_email !== null && (
              <p className="txt-faint text-[11.5px]">{row.actor_email}</p>
            )}
          </div>
        ),
      },
      {
        key: 'action',
        label: 'Action',
        minWidth: '11rem',
        render: (row) => (
          <span className="inline-flex items-center gap-1.5">
            {isSecurityAction(row.action) && (
              <ShieldAlert
                className="h-3.5 w-3.5 shrink-0 text-amber-500"
                aria-label="Security-relevant"
              />
            )}
            <span className="txt text-[12.5px] font-medium">{actionLabel(row.action)}</span>
          </span>
        ),
      },
      {
        key: 'entity',
        label: 'Record',
        minWidth: '12rem',
        hideBelow: 'md',
        render: (row) => {
          if (row.entity_type === null) return <span className="txt-faint">—</span>;
          return (
            <div>
              <p className="txt text-[12.5px]">{row.entity_label ?? row.entity_id ?? '—'}</p>
              <p className="txt-faint text-[11.5px]">{actionLabel(row.entity_type)}</p>
            </div>
          );
        },
      },
      {
        key: 'details',
        label: 'Details',
        minWidth: '12rem',
        hideBelow: 'lg',
        render: (row) => (
          <span className="txt-muted text-[12.5px]">{summariseDetails(row)}</span>
        ),
      },
      {
        key: 'status',
        label: 'Outcome',
        align: 'center',
        minWidth: '6rem',
        render: (row) => (
          <StatusBadge label={actionLabel(row.status)} variant={statusVariantFor(row.status)} />
        ),
      },
    ],
    [],
  );

  const header = (
    <div className="flex items-center gap-3.5">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-slate-600 to-gray-800">
        <ScrollText className="h-5 w-5 text-white" />
      </div>
      <div>
        <h1 className="font-display txt text-[22px] font-extrabold">Audit Logs</h1>
        <p className="txt-muted mt-0.5 text-[13px]">Who did what, and when.</p>
      </div>
    </div>
  );

  // Permission is enforced by the API on every request; this only decides what
  // to render instead of a table the caller would receive a 403 from.
  //
  // Deliberately *not* the "not configured" state: the backend exists and is
  // recording. Saying otherwise would tell someone without access that the
  // system keeps no audit trail, which is both untrue and exactly the wrong
  // thing for them to believe.
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
              You do not have access to the audit trail
            </p>
            <p className="txt-muted mx-auto mt-1.5 max-w-lg text-[12.5px] leading-relaxed">
              The trail records sign-ins, permission changes and record deletions for
              everyone in this organization, so reading it is granted deliberately rather
              than by default. Ask an administrator if you need access.
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

      {/* ---- Filters ---- */}
      <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">
              Action
            </span>
            <FilterSelect
              value={filters.action}
              onChange={(event) => update({ action: event.target.value })}
              options={[
                ANY_ACTION,
                ...(options?.actions ?? []).map((value) => ({
                  value,
                  label: actionLabel(value),
                })),
              ]}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">
              Record type
            </span>
            <FilterSelect
              value={filters.entityType}
              onChange={(event) => update({ entityType: event.target.value })}
              options={[
                ANY_ENTITY,
                ...(options?.entity_types ?? []).map((value) => ({
                  value,
                  label: actionLabel(value),
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
                ...(options?.statuses ?? []).map((value) => ({
                  value,
                  label: actionLabel(value),
                })),
              ]}
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

        {options?.recording_since != null && (
          <p className="txt-faint text-[11.5px]">
            Recording since {formatTimestamp(options.recording_since).date}. Records are
            append-only and cannot be edited or removed through this application.
          </p>
        )}
        {optionsError !== null && (
          <p className="txt-faint text-[11.5px]">{optionsError}</p>
        )}
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
                title={filtered ? 'No records match those filters' : 'Nothing recorded yet'}
                hint={
                  filtered
                    ? 'Widen the date range, or clear the filters to see the whole trail.'
                    : 'Sign-ins, permission changes and record edits appear here as they happen.'
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
        title={selected ? actionLabel(selected.action) : ''}
        subtitle={selected ? formatTimestamp(selected.created_at).date : undefined}
        width="max-w-lg"
      >
        {selected !== null && <AuditDetail entry={selected} />}
      </SlideDrawer>
    </div>
  );
}

/* ------------------------------------------------------------------
   Detail panel
   ------------------------------------------------------------------ */

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="txt-faint text-[11px] font-bold uppercase tracking-wider">{label}</span>
      <span className="txt break-words text-[13px]">{value}</span>
    </div>
  );
}

function AuditDetail({ entry }: { entry: AuditLogEntry }) {
  const { date, time } = formatTimestamp(entry.created_at);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <Field label="When" value={`${date} ${time}`} />
        <Field
          label="Outcome"
          value={
            <StatusBadge
              label={actionLabel(entry.status)}
              variant={statusVariantFor(entry.status)}
            />
          }
        />
        <Field label="Who" value={entry.actor_name ?? entry.actor_email ?? 'System'} />
        <Field label="Email" value={entry.actor_email ?? '—'} />
        <Field label="Module" value={actionLabel(entry.module)} />
        <Field
          label="Record type"
          value={entry.entity_type ? actionLabel(entry.entity_type) : '—'}
        />
      </div>

      <div>
        <SectionHeader title="Record" />
        <div className="mt-2 grid grid-cols-1 gap-3">
          <Field label="Name at the time" value={entry.entity_label ?? '—'} />
          <Field
            label="Identifier"
            value={
              <code className="txt-muted text-[11.5px]">{entry.entity_id ?? '—'}</code>
            }
          />
        </div>
      </div>

      <div>
        <SectionHeader title="Details" />
        {entry.details === null ? (
          <p className="txt-faint mt-2 text-[12.5px]">No additional detail was recorded.</p>
        ) : (
          // Wide payloads scroll inside their own container so the drawer never
          // does. Rendered as-is because the values were already redacted
          // server-side: credentials are absent and contact details are masked.
          <pre
            className="surface-2 bd txt mt-2 overflow-x-auto rounded-xl border p-3 text-[11.5px] leading-relaxed"
            style={{ maxHeight: '18rem' }}
          >
            {JSON.stringify(entry.details, null, 2)}
          </pre>
        )}
      </div>

      <div>
        <SectionHeader title="Request" />
        <div className="mt-2 grid grid-cols-1 gap-3">
          <Field
            label="Correlation ID"
            value={
              <code className="txt-muted text-[11.5px]">{entry.request_id ?? '—'}</code>
            }
          />
          <Field label="IP address" value={entry.ip_address ?? '—'} />
          <Field
            label="User agent"
            value={<span className="txt-muted text-[11.5px]">{entry.user_agent ?? '—'}</span>}
          />
        </div>
      </div>
    </div>
  );
}
