'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, RotateCcw, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { type SortDirection } from '@/components/crm/tables/DataTable';
import NbaKpiSummary from '@/components/crm/ai/nba/NbaKpiSummary';
import NbaFilterToolbar from '@/components/crm/ai/nba/NbaFilterToolbar';
import NbaTable from '@/components/crm/ai/nba/NbaTable';
import NbaDetailsDrawer from '@/components/crm/ai/nba/NbaDetailsDrawer';
import NbaMessageSheet, { type MessageKind } from '@/components/crm/ai/nba/NbaMessageSheet';
import NbaScheduleMeetingSheet from '@/components/crm/ai/nba/NbaScheduleMeetingSheet';
import { type NbaAction } from '@/components/crm/ai/nba/NbaRowActions';
import TablePagination from '@/components/crm/ai/shared/TablePagination';
import AiEmptyState from '@/components/crm/ai/shared/AiEmptyState';
import {
  buildNbaDetail,
  generateMockNBARecommendation,
  getMockNBADetail,
  getMockNBARecords,
  type NbaDetail,
  type NbaRecord,
} from '@/features/ai/next-best-action';
import {
  EMPTY_FILTERS,
  applyNbaFilters,
  buildEntityOptions,
  countActiveFilters,
  type NbaFilters,
} from '@/features/ai/next-best-action/filters';
import { formatDate } from '@/features/ai/shared/format';

/* ============================================================
   NEXT BEST ACTION
   AI-assisted sales intelligence workspace. Filtering, sorting,
   pagination and every demo action run entirely on local state
   — there are no API routes, server actions or AI calls here.
   ============================================================ */

type SheetState =
  | { kind: 'none' }
  | { kind: 'message'; messageKind: MessageKind; record: NbaRecord; detail: NbaDetail }
  | { kind: 'meeting'; record: NbaRecord };

export default function NextBestActionPage() {
  /* ---- Data ---- */
  const [records, setRecords] = useState<NbaRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  /* ---- Table state ---- */
  const [filters, setFilters] = useState<NbaFilters>(EMPTY_FILTERS);
  const [sortKey, setSortKey] = useState<string | null>('priority');
  const [sortDir, setSortDir] = useState<SortDirection>('asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [openActionId, setOpenActionId] = useState<string | null>(null);

  /* ---- Drawer and sheets ---- */
  const [selected, setSelected] = useState<NbaRecord | null>(null);
  const [detail, setDetail] = useState<NbaDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [sheet, setSheet] = useState<SheetState>({ kind: 'none' });
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  /* ---- Load the working set ---- */
  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      setRecords(await getMockNBARecords());
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /* ---- Derived data ---- */
  const { companyOptions, salespersonOptions } = useMemo(
    () => buildEntityOptions(records),
    [records],
  );

  const activeFilterCount = countActiveFilters(filters);

  const filtered = useMemo(() => applyNbaFilters(records, filters), [records, filters]);

  const sorted = useMemo(() => {
    if (!sortKey || !sortDir) return filtered;

    // Priority sorts by severity rather than alphabetically.
    const priorityRank: Record<string, number> = { Critical: 0, High: 1, Medium: 2, Low: 3 };
    const riskRank: Record<string, number> = { Critical: 0, High: 1, Medium: 2, Low: 3 };

    return [...filtered].sort((a, b) => {
      let comparison: number;

      if (sortKey === 'priority') {
        comparison = priorityRank[a.priority] - priorityRank[b.priority];
      } else if (sortKey === 'dealRisk') {
        comparison = riskRank[a.dealRisk] - riskRank[b.dealRisk];
      } else {
        const left = (a as unknown as Record<string, unknown>)[sortKey];
        const right = (b as unknown as Record<string, unknown>)[sortKey];
        comparison =
          typeof left === 'number' && typeof right === 'number'
            ? left - right
            : String(left ?? '').localeCompare(String(right ?? ''));
      }

      return sortDir === 'asc' ? comparison : -comparison;
    });
  }, [filtered, sortKey, sortDir]);

  const paginated = useMemo(
    () => sorted.slice((page - 1) * pageSize, page * pageSize),
    [sorted, page, pageSize],
  );

  // Keep the page in range when filtering shrinks the result set.
  useEffect(() => {
    const lastPage = Math.max(1, Math.ceil(sorted.length / pageSize));
    if (page > lastPage) setPage(lastPage);
  }, [sorted.length, pageSize, page]);

  /* ---- Handlers ---- */
  const handleFilterChange = useCallback(
    <K extends keyof NbaFilters>(key: K, value: NbaFilters[K]) => {
      setFilters(previous => ({ ...previous, [key]: value }));
      setPage(1);
    },
    [],
  );

  const handleResetFilters = useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }, []);

  const handleSort = useCallback((key: string) => {
    setSortKey(previousKey => {
      if (previousKey === key) {
        setSortDir(direction => (direction === 'asc' ? 'desc' : direction === 'desc' ? null : 'asc'));
        return key;
      }
      setSortDir('asc');
      return key;
    });
  }, []);

  const openDetails = useCallback(async (record: NbaRecord) => {
    setSelected(record);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await getMockNBADetail(record));
    } catch {
      toast.error('Opportunity intelligence could not be loaded');
      setSelected(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const markCompleted = useCallback((record: NbaRecord) => {
    setRecords(previous =>
      previous.map(item => (item.id === record.id ? { ...item, status: 'Completed' } : item)),
    );
    setSelected(previous =>
      previous && previous.id === record.id ? { ...previous, status: 'Completed' } : previous,
    );
    toast.success(`Marked completed — ${record.leadName} · ${record.company}`);
  }, []);

  const regenerate = useCallback(async (record: NbaRecord) => {
    setRegeneratingId(record.id);
    try {
      const next = await generateMockNBARecommendation(record);
      const updated: NbaRecord = { ...record, ...next };

      setRecords(previous => previous.map(item => (item.id === record.id ? updated : item)));
      setSelected(previous => (previous && previous.id === record.id ? updated : previous));
      setDetail(previous => (previous?.recordId === record.id ? buildNbaDetail(updated) : previous));

      toast.success('Recommendation regenerated');
    } catch {
      toast.error('Recommendation could not be regenerated');
    } finally {
      setRegeneratingId(null);
    }
  }, []);

  const handleAction = useCallback(
    (action: NbaAction, record: NbaRecord) => {
      switch (action) {
        case 'view':
          void openDetails(record);
          break;
        case 'email':
          setSheet({ kind: 'message', messageKind: 'email', record, detail: buildNbaDetail(record) });
          break;
        case 'whatsapp':
          setSheet({ kind: 'message', messageKind: 'whatsapp', record, detail: buildNbaDetail(record) });
          break;
        case 'meeting':
          setSheet({ kind: 'meeting', record });
          break;
        case 'complete':
          markCompleted(record);
          break;
        case 'regenerate':
          void regenerate(record);
          break;
        case 'open-lead':
          // Disabled in the menu — demo records have no corresponding lead route.
          break;
      }
    },
    [openDetails, markCompleted, regenerate],
  );

  const handleScheduleMeeting = useCallback(
    (record: NbaRecord, form: { title: string; date: string; time: string }) => {
      setRecords(previous =>
        previous.map(item =>
          item.id === record.id
            ? { ...item, status: 'Scheduled', nextFollowUp: form.date || item.nextFollowUp }
            : item,
        ),
      );
      setSheet({ kind: 'none' });
      toast.success(
        `Meeting scheduled — ${form.title} on ${formatDate(form.date)} at ${form.time}`,
        { description: 'Demonstration only — no calendar invitation was created.' },
      );
    },
    [],
  );

  /* ---- Render ---- */
  return (
    <div className="space-y-5 p-6 lg:p-8">
      {/* ── Page header ── */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-600 to-indigo-600">
            <Sparkles className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold leading-tight tracking-tight">
              Next Best Action
            </h1>
            <p className="txt-muted mt-0.5 text-[13px] font-medium">
              AI-generated recommendations to maximise deal conversion and customer engagement.
            </p>
          </div>
        </div>
      </header>

      {loadError ? (
        <div className="surface bd rounded-2xl border p-6">
          <AiEmptyState
            icon={AlertCircle}
            title="Recommendations could not be loaded"
            description="Something went wrong preparing the working set. Please try again."
            action={
              <button
                type="button"
                onClick={() => void load()}
                className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
                style={{ background: 'var(--accent)' }}
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Retry
              </button>
            }
          />
        </div>
      ) : (
        <>
          <NbaKpiSummary records={records} />

          <NbaFilterToolbar
            filters={filters}
            onChange={handleFilterChange}
            onReset={handleResetFilters}
            companyOptions={companyOptions}
            salespersonOptions={salespersonOptions}
            activeFilterCount={activeFilterCount}
            resultCount={sorted.length}
            totalCount={records.length}
          />

          <div className="surface bd overflow-hidden rounded-2xl border">
            <NbaTable
              records={paginated}
              loading={loading}
              sortKey={sortKey}
              sortDirection={sortDir}
              onSort={handleSort}
              onRowClick={record => void openDetails(record)}
              onAction={handleAction}
              openActionId={openActionId}
              onOpenActionChange={setOpenActionId}
              regeneratingId={regeneratingId}
              hasActiveFilters={activeFilterCount > 0}
              onResetFilters={handleResetFilters}
            />

            {!loading && sorted.length > 0 && (
              <TablePagination
                page={page}
                pageSize={pageSize}
                totalItems={sorted.length}
                onPageChange={setPage}
                onPageSizeChange={size => {
                  setPageSize(size);
                  setPage(1);
                }}
              />
            )}
          </div>
        </>
      )}

      {/* ── Details drawer ── */}
      <NbaDetailsDrawer
        open={selected !== null}
        record={selected}
        detail={detail}
        loading={detailLoading}
        regenerating={selected !== null && regeneratingId === selected.id}
        onClose={() => {
          setSelected(null);
          setDetail(null);
        }}
        onMarkCompleted={markCompleted}
        onRegenerate={record => void regenerate(record)}
      />

      {/* ── Generated message preview ── */}
      <NbaMessageSheet
        open={sheet.kind === 'message'}
        kind={sheet.kind === 'message' ? sheet.messageKind : 'email'}
        record={sheet.kind === 'message' ? sheet.record : null}
        detail={sheet.kind === 'message' ? sheet.detail : null}
        onClose={() => setSheet({ kind: 'none' })}
      />

      {/* ── Demo meeting scheduler ── */}
      <NbaScheduleMeetingSheet
        open={sheet.kind === 'meeting'}
        record={sheet.kind === 'meeting' ? sheet.record : null}
        onClose={() => setSheet({ kind: 'none' })}
        onSchedule={handleScheduleMeeting}
      />
    </div>
  );
}
