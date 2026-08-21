'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckCircle2, ListChecks, Loader2 } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { usePermissions } from '@/context/AuthContext';
import { useCollection } from '@/features/shared/hooks/useCollection';
import { listLeadSources, type LeadSource } from '@/features/crm/lead-sources';
import {
  SCORECARD_UNAVAILABLE,
  STAGE_LABELS,
  listQualificationQueue,
  markQualified,
  qualificationStage,
  type Lead,
  type LeadStatus,
} from '@/features/crm/qualification';
import { useEffect } from 'react';

/* ============================================================
   QUALIFICATION

   A working view over real leads, not a table of its own.

   What is real here: the queue, its statuses, its owners, its
   sources, and the "mark qualified" action — all of which go
   through the same lead endpoints the Leads screen uses, with
   the same state machine enforced by the backend.

   What is deliberately absent: BANT / MEDDICC scoring. It needs
   a `QualificationRecord` table that has not been built, so
   there is nowhere to persist budget, authority, need or
   timeline. The previous version of this page displayed five
   invented leads with invented scores; a queue that lies about
   who is qualified is worse than an empty one.
   ============================================================ */

const STATUS_OPTIONS = [
  { value: '', label: 'All open leads' },
  { value: 'NEW', label: 'New' },
  { value: 'CONTACTED', label: 'Contacted' },
  { value: 'QUALIFIED', label: 'Qualified' },
  { value: 'PROPOSAL_SENT', label: 'Proposal sent' },
  { value: 'NEGOTIATION', label: 'Negotiation' },
];

type ViewMode = 'queue' | 'table';

export default function QualificationPage() {
  const router = useRouter();
  const { can } = usePermissions();
  const mayEdit = can('leads', 'EDIT');
  const mayViewSources = can('lead_sources', 'VIEW');

  const [view, setView] = useState<ViewMode>('queue');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () =>
      listQualificationQueue({
        page,
        page_size: 25,
        search: search.trim() || null,
        status: (statusFilter || null) as LeadStatus | null,
        sort_by: 'created_at',
        sort_dir: 'desc',
      }),
    [page, search, statusFilter],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Lead>(
    fetcher,
    [page, search, statusFilter],
    { errorMessage: 'Something went wrong loading the qualification queue.' },
  );

  /* ---- Source names, so the queue shows where a lead came from ---- */
  const [sources, setSources] = useState<LeadSource[]>([]);
  useEffect(() => {
    if (!mayViewSources) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await listLeadSources({ page_size: 200 });
        if (!cancelled) setSources(result.data);
      } catch {
        // The queue still renders; the source column shows a dash.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewSources]);

  const sourceNames = useMemo(
    () => new Map(sources.map((source) => [source.id, source.name])),
    [sources],
  );

  /* The id of the lead currently being qualified. One request at a time, so
     a double click cannot fire the transition twice. */
  const [working, setWorking] = useState<string | null>(null);
  const pending = working !== null;

  const handleQualify = async (lead: Lead) => {
    setWorking(lead.id);
    try {
      await markQualified(lead.id);
      notifySuccess('Lead qualified', [lead.first_name, lead.last_name].join(' ').trim());
      reload();
    } catch (caught) {
      notifyError(caught, 'The lead could not be qualified.');
    } finally {
      setWorking(null);
    }
  };

  /* With no status filter the API returns every lead, including the closed
     ones. The queue is about open work, so those are dropped here. */
  const queue = useMemo(
    () => (statusFilter ? items : items.filter((lead) => qualificationStage(lead) !== 'CLOSED')),
    [items, statusFilter],
  );

  const columns = useMemo<ColumnDef<Lead>[]>(
    () => [
      {
        key: 'name',
        label: 'Lead',
        minWidth: '190px',
        render: (row) => (
          <div className="flex flex-col">
            <span className="txt text-[13px] font-semibold">
              {row.first_name} {row.last_name}
            </span>
            {row.company && <span className="txt-faint mt-0.5 text-[11.5px]">{row.company}</span>}
          </div>
        ),
      },
      {
        key: 'lead_source_id',
        label: 'Source',
        hideBelow: 'md',
        render: (row) =>
          row.lead_source_id ? (
            <span className="txt-muted text-[12.5px]">
              {sourceNames.get(row.lead_source_id) ?? '—'}
            </span>
          ) : (
            <span className="txt-faint">—</span>
          ),
      },
      {
        key: 'priority',
        label: 'Priority',
        hideBelow: 'lg',
        render: (row) =>
          row.priority ? (
            <StatusBadge label={humanize(row.priority)} variant={statusVariant(row.priority)} />
          ) : (
            <span className="txt-faint">—</span>
          ),
      },
      {
        key: 'status',
        label: 'Status',
        render: (row) => (
          <StatusBadge label={humanize(row.status)} variant={statusVariant(row.status)} />
        ),
      },
      {
        key: 'actions',
        label: '',
        align: 'right',
        render: (row) => (
          <div className="flex items-center justify-end gap-1">
            {mayEdit && row.status === 'CONTACTED' && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  void handleQualify(row);
                }}
                disabled={pending}
                className="ctl bd flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] font-semibold transition hover:opacity-80 disabled:opacity-50"
              >
                {pending && working === row.id ? (
                  <Loader2 className="h-3 w-3 motion-safe:animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3 w-3" />
                )}
                Qualify
              </button>
            )}
            <button
              type="button"
              aria-label={`Open ${row.first_name} ${row.last_name}`}
              onClick={(event) => {
                event.stopPropagation();
                router.push(`/qualification/${row.id}`);
              }}
              className="ctl rounded-lg p-1.5 transition hover:opacity-70"
            >
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mayEdit, pending, working, sourceNames],
  );

  const emptyState = (
    <ListEmpty
      title="Nothing waiting for qualification"
      hint={
        search || statusFilter
          ? 'No lead matches those filters.'
          : 'New and contacted leads appear here until they are qualified or closed.'
      }
    />
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-emerald-500 to-green-600">
            <ListChecks className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Qualification</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Leads waiting to be worked, newest first.
            </p>
          </div>
        </div>
        <div className="bd flex rounded-lg border p-0.5">
          <button
            type="button"
            onClick={() => setView('queue')}
            aria-pressed={view === 'queue'}
            className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold transition ${
              view === 'queue' ? 'surface-2 txt' : 'txt-faint'
            }`}
          >
            Queue
          </button>
          <button
            type="button"
            onClick={() => setView('table')}
            aria-pressed={view === 'table'}
            className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold transition ${
              view === 'table' ? 'surface-2 txt' : 'txt-faint'
            }`}
          >
            Table
          </button>
        </div>
      </div>

      <PartialDataNotice>{SCORECARD_UNAVAILABLE}</PartialDataNotice>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchInput
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder="Search leads…"
        />
        <FilterSelect
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
          options={STATUS_OPTIONS}
        />
        {refreshing && (
          <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Refreshing" />
        )}
        <div className="ml-auto">
          <ResultCount shown={queue.length} total={pagination?.total ?? 0} />
        </div>
      </div>

      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : view === 'table' ? (
        <DataTable
          columns={columns}
          data={queue}
          rowKey={(row) => row.id}
          loading={status === 'loading'}
          skeletonRows={6}
          onRowClick={(row) => router.push(`/qualification/${row.id}`)}
          emptyState={emptyState}
        />
      ) : status === 'loading' ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }, (_, index) => (
            <div
              key={index}
              className="motion-safe:animate-pulse h-[76px] rounded-2xl"
              style={{ background: 'var(--surface-2)' }}
            />
          ))}
        </div>
      ) : queue.length === 0 ? (
        <div className="surface bd rounded-2xl border">{emptyState}</div>
      ) : (
        <div className="space-y-3">
          {queue.map((lead) => (
            <div
              key={lead.id}
              className="surface bd flex flex-wrap items-center gap-4 rounded-2xl border p-4"
            >
              <button
                type="button"
                onClick={() => router.push(`/qualification/${lead.id}`)}
                className="min-w-0 flex-1 text-left"
              >
                <p className="txt text-[14px] font-bold">
                  {lead.first_name} {lead.last_name}
                </p>
                <p className="txt-muted mt-0.5 text-[12.5px]">
                  {[
                    lead.company,
                    lead.lead_source_id ? sourceNames.get(lead.lead_source_id) : null,
                  ]
                    .filter(Boolean)
                    .join(' · ') || 'No company recorded'}
                </p>
              </button>

              <div className="flex items-center gap-2">
                <span className="txt-faint text-[11.5px] font-medium">
                  {STAGE_LABELS[qualificationStage(lead)]}
                </span>
                <StatusBadge label={humanize(lead.status)} variant={statusVariant(lead.status)} />
                {lead.priority && (
                  <StatusBadge
                    label={humanize(lead.priority)}
                    variant={statusVariant(lead.priority)}
                  />
                )}
              </div>

              <div className="flex items-center gap-2">
                {mayEdit && lead.status === 'CONTACTED' && (
                  <button
                    type="button"
                    onClick={() => void handleQualify(lead)}
                    disabled={pending}
                    className="ctl bd flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80 disabled:opacity-50"
                  >
                    {pending && working === lead.id ? (
                      <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    )}
                    Qualify
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => router.push(`/qualification/${lead.id}`)}
                  className="ctl bd flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition hover:opacity-80"
                >
                  Review <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
