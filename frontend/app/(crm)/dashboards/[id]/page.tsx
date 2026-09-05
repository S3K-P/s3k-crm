'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  LayoutGrid,
  Plus,
  RefreshCw,
  Settings2,
  Trash2,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { ListEmpty, ListError } from '@/components/crm/shared/ListStates';
import {
  ReportChart,
  chartHasData,
  ReportMetric,
  ReportTable,
} from '@/components/crm/reports/ReportView';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  WIDTH_CHOICES,
  addComponent,
  deleteDashboard,
  getDashboard,
  removeComponent,
  renderDashboard,
  reorderComponents,
  unavailableMessage,
  updateComponent,
  type ComponentDisplay,
  type DashboardComponentData,
  type DashboardData,
  type DashboardDetail,
} from '@/features/crm/dashboards';
import { listSavedReports, type SavedReport } from '@/features/crm/reports/library';

/* ============================================================
   ONE DASHBOARD

   Two modes over the same layout. Viewing runs every tile and
   draws it; arranging shows the same grid with controls on each
   tile instead of data.

   The grid is a twelve-column flow, matching the backend's
   `DASHBOARD_GRID_COLUMNS`. On a narrow screen every tile spans
   the full width regardless of its stored width — a third of a
   phone is not a chart, it is a smudge.

   Reordering is by explicit up/down buttons rather than drag.
   Drag-and-drop needs a pointer, and this is the one editing
   affordance on the screen that has to work on a tablet.
   ============================================================ */

/** Tailwind cannot see a computed class name, so the spans are spelled out. */
const SPAN_CLASS: Record<number, string> = {
  1: 'lg:col-span-1',
  2: 'lg:col-span-2',
  3: 'lg:col-span-3',
  4: 'lg:col-span-4',
  5: 'lg:col-span-5',
  6: 'lg:col-span-6',
  7: 'lg:col-span-7',
  8: 'lg:col-span-8',
  9: 'lg:col-span-9',
  10: 'lg:col-span-10',
  11: 'lg:col-span-11',
  12: 'lg:col-span-12',
};

const DISPLAY_CHOICES: { value: ComponentDisplay; label: string }[] = [
  { value: 'CHART', label: 'Chart' },
  { value: 'TABLE', label: 'Table' },
  { value: 'METRIC', label: 'Single number' },
];

export default function DashboardDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const confirm = useConfirm();
  const dashboardId = params.id;

  const [detail, setDetail] = useState<DashboardDetail | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [arranging, setArranging] = useState(false);
  const [reload, setReload] = useState(0);

  const [savedReports, setSavedReports] = useState<SavedReport[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [chosenReport, setChosenReport] = useState('');
  const [chosenDisplay, setChosenDisplay] = useState<ComponentDisplay>('CHART');
  const [chosenWidth, setChosenWidth] = useState(6);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Fetching lives in the effect rather than in a callback the effect calls:
  // `react-hooks/set-state-in-effect` reads through a `useCallback` and flags
  // the setState it can reach, and it is right to — a response that arrives
  // after the user has navigated away should not touch state, which is what
  // the `cancelled` flag is for. Everything else asks for a reload by bumping
  // the counter.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [layout, rendered] = await Promise.all([
          getDashboard(dashboardId),
          renderDashboard(dashboardId),
        ]);
        if (cancelled) return;
        setDetail(layout);
        setData(rendered);
        setError(null);
      } catch (cause) {
        if (!cancelled) {
          setError(describeApiError(cause, 'Unable to load this dashboard.'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dashboardId, reload]);

  const load = useCallback(() => {
    setLoading(true);
    setReload(count => count + 1);
  }, []);

  const openAdd = async () => {
    setFormError(null);
    setChosenReport('');
    setChosenDisplay('CHART');
    setChosenWidth(6);
    setAddOpen(true);
    try {
      const page = await listSavedReports();
      setSavedReports(page.data);
    } catch (cause) {
      setFormError(describeApiError(cause, 'Unable to load your saved reports.'));
    }
  };

  const submitAdd = async () => {
    setBusy(true);
    setFormError(null);
    try {
      await addComponent(dashboardId, {
        saved_report_id: chosenReport,
        display: chosenDisplay,
        width: chosenWidth,
      });
      setAddOpen(false);
      load();
    } catch (cause) {
      setFormError(describeApiError(cause, 'Unable to add this tile.'));
    } finally {
      setBusy(false);
    }
  };

  const changeTile = async (
    componentId: string,
    patch: { display?: ComponentDisplay; width?: number },
  ) => {
    try {
      await updateComponent(dashboardId, componentId, patch);
      load();
    } catch (cause) {
      setError(describeApiError(cause, 'Unable to update this tile.'));
    }
  };

  const dropTile = async (componentId: string, title: string) => {
    const answer = await confirm({
      title: `Remove “${title}”?`,
      description: 'The saved report itself is not deleted.',
      confirmLabel: 'Remove',
      tone: 'danger',
    });
    if (!answer) return;
    try {
      await removeComponent(dashboardId, componentId);
      load();
    } catch (cause) {
      setError(describeApiError(cause, 'Unable to remove this tile.'));
    }
  };

  const move = async (index: number, direction: -1 | 1) => {
    if (!detail) return;
    const order = detail.components.map(component => component.id);
    const target = index + direction;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    try {
      await reorderComponents(dashboardId, order);
      load();
    } catch (cause) {
      setError(describeApiError(cause, 'Unable to reorder the tiles.'));
    }
  };

  const dropDashboard = async () => {
    if (!detail) return;
    const answer = await confirm({
      title: `Delete “${detail.name}”?`,
      description: 'The tiles go with it. The saved reports are not deleted.',
      confirmLabel: 'Delete',
      tone: 'danger',
    });
    if (!answer) return;
    try {
      await deleteDashboard(dashboardId);
      router.push('/dashboards');
    } catch (cause) {
      setError(describeApiError(cause, 'Unable to delete this dashboard.'));
    }
  };

  const tiles = data?.components ?? [];

  return (
    <div className="flex h-full flex-col space-y-5 p-4 sm:p-6 lg:p-8">
      <div>
        <Link
          href="/dashboards"
          className="txt-faint hover:txt inline-flex items-center gap-1.5 text-[12px] font-semibold"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> All dashboards
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-500 to-indigo-600">
            <LayoutGrid className="h-5 w-5 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="font-display txt truncate text-[22px] font-extrabold leading-tight tracking-tight">
              {detail?.name ?? 'Dashboard'}
            </h1>
            {detail?.description && (
              <p className="txt-muted mt-0.5 truncate text-[13px] font-medium">
                {detail.description}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => load()}
            disabled={loading}
            className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80 disabled:opacity-60"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setArranging(value => !value)}
            aria-pressed={arranging}
            className={cn(
              'ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80',
              arranging && 'border-[var(--accent)] text-[var(--accent)]',
            )}
          >
            <Settings2 className="h-3.5 w-3.5" />
            {arranging ? 'Done' : 'Arrange'}
          </button>
          <button
            type="button"
            onClick={() => void openAdd()}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <Plus className="h-4 w-4" /> Add tile
          </button>
          {arranging && (
            <button
              type="button"
              onClick={() => void dropDashboard()}
              className="ctl bd inline-flex items-center rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:text-rose-500"
              aria-label="Delete this dashboard"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {error && <ListError message={error} onRetry={() => load()} />}

      {!error && tiles.length === 0 && !loading && (
        <ListEmpty
          title="No tiles yet"
          hint="Add a saved report to start building this dashboard."
        />
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {tiles.map((tile, index) => (
          <div
            key={tile.id}
            className={cn(
              'surface bd flex flex-col rounded-2xl border p-5',
              SPAN_CLASS[tile.width] ?? SPAN_CLASS[6],
            )}
          >
            <div className="mb-3 flex items-start justify-between gap-2">
              <h2 className="txt font-display truncate text-[14px] font-bold">
                {tile.title}
              </h2>
              {arranging && (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void move(index, -1)}
                    disabled={index === 0}
                    aria-label={`Move ${tile.title} earlier`}
                    className="txt-faint hover:txt disabled:opacity-30"
                  >
                    <ChevronUp className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void move(index, 1)}
                    disabled={index === tiles.length - 1}
                    aria-label={`Move ${tile.title} later`}
                    className="txt-faint hover:txt disabled:opacity-30"
                  >
                    <ChevronDown className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void dropTile(tile.id, tile.title)}
                    aria-label={`Remove ${tile.title}`}
                    className="txt-faint hover:text-rose-500"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>

            {arranging ? (
              <div className="flex flex-wrap gap-2">
                <label className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">
                  Show as
                  <select
                    value={tile.display}
                    onChange={event =>
                      void changeTile(tile.id, {
                        display: event.target.value as ComponentDisplay,
                      })
                    }
                    className="ctl txt mt-1 block px-2.5 py-1.5 text-[12.5px] font-normal normal-case tracking-normal"
                  >
                    {DISPLAY_CHOICES.map(choice => (
                      <option key={choice.value} value={choice.value}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">
                  Width
                  <select
                    value={tile.width}
                    onChange={event =>
                      void changeTile(tile.id, { width: Number(event.target.value) })
                    }
                    className="ctl txt mt-1 block px-2.5 py-1.5 text-[12.5px] font-normal normal-case tracking-normal"
                  >
                    {WIDTH_CHOICES.map(choice => (
                      <option key={choice.value} value={choice.value}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ) : (
              <TileBody tile={tile} />
            )}
          </div>
        ))}
      </div>

      {data && tiles.length > 0 && (
        <p className="txt-faint text-[11.5px]">
          Generated {new Date(data.generated_at).toLocaleString()}
        </p>
      )}

      <SlideDrawer
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add a tile"
        subtitle="Tiles are built from saved reports."
        footer={
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[12.5px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || !chosenReport}
              onClick={() => void submitAdd()}
              className="rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {/* Not "Add tile": that is the toolbar button that opened this
                  drawer, and two controls with the same accessible name on
                  one screen is ambiguous to anyone navigating by name. */}
              {busy ? 'Adding…' : 'Add to dashboard'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          {formError && (
            <p role="alert" className="text-[12.5px] text-rose-500">
              {formError}
            </p>
          )}
          {savedReports.length === 0 && !formError && (
            <p className="txt-muted text-[12.5px]">
              You have no saved reports yet. Save one from the{' '}
              <Link href="/reports" className="text-[var(--accent)] underline">
                Reports
              </Link>{' '}
              screen first.
            </p>
          )}
          {savedReports.length > 0 && (
            <>
              <label className="block">
                <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
                  Report
                </span>
                <select
                  value={chosenReport}
                  onChange={event => setChosenReport(event.target.value)}
                  className="ctl txt w-full px-3 py-2 text-[13px]"
                >
                  <option value="">Choose a saved report…</option>
                  {savedReports.map(report => (
                    <option key={report.id} value={report.id}>
                      {report.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
                  Show as
                </span>
                <select
                  value={chosenDisplay}
                  onChange={event =>
                    setChosenDisplay(event.target.value as ComponentDisplay)
                  }
                  className="ctl txt w-full px-3 py-2 text-[13px]"
                >
                  {DISPLAY_CHOICES.map(choice => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
                  Width
                </span>
                <select
                  value={chosenWidth}
                  onChange={event => setChosenWidth(Number(event.target.value))}
                  className="ctl txt w-full px-3 py-2 text-[13px]"
                >
                  {WIDTH_CHOICES.map(choice => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
        </div>
      </SlideDrawer>
    </div>
  );
}

/** A rendered tile, or the reason there isn't one. */
function TileBody({ tile }: { tile: DashboardComponentData }) {
  if (tile.unavailable !== null) {
    return (
      <div className="txt-muted flex items-start gap-2 py-4 text-[12.5px]">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"
          aria-hidden="true"
        />
        <p>{unavailableMessage(tile.unavailable)}</p>
      </div>
    );
  }
  if (tile.result === null) return null;

  if (tile.display === 'METRIC') return <ReportMetric result={tile.result} />;
  if (tile.display === 'TABLE') {
    // Capped: a tile is a glance, and the Reports screen is where the whole
    // table lives. The footer says how many rows were left out.
    return <ReportTable result={tile.result} maxRows={6} />;
  }

  // A chart tile whose report has no chart hint, or whose rows are all zero,
  // falls back to the table rather than leaving an empty box. The zero case is
  // not hypothetical: it is exactly what a rep sees on a shared dashboard
  // built from deals they do not own.
  return chartHasData(tile.result) ? (
    <ReportChart result={tile.result} compact />
  ) : (
    <ReportTable result={tile.result} maxRows={6} />
  );
}
