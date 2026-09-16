'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  AlertTriangle,
  ArrowLeft,
  CalendarRange,
  ChevronDown,
  ChevronUp,
  GripVertical,
  LayoutGrid,
  Plus,
  RefreshCw,
  Settings2,
  Trash2,
  X,
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

   Reordering (Checkpoint 5) is by drag *and* by explicit up/down
   buttons — not one or the other. `@dnd-kit`'s sortable strategy
   ships a keyboard sensor as well as a pointer one, so drag is
   not the accessibility regression plain HTML5 drag-and-drop
   would have been; the buttons stay anyway, as the one path that
   needs no explanation on a touchscreen where a press-and-hold
   is easy to trigger by accident. Both call the identical
   `reorderComponents` — there is one source of truth for order,
   not two competing ones.

   A dashboard-wide date filter (Checkpoint 5) narrows every tile
   whose report has a date dimension; see `DateFilterBar` and
   `date_filter_applied` on each rendered tile.
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
  // Checkpoint 5: a dashboard-wide date filter, applied per tile only where
  // the tile's own report has a date dimension — see `DateFilterBar` and
  // `DashboardComponentData.date_filter_applied`.
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

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
          renderDashboard(dashboardId, { date_from: dateFrom || null, date_to: dateTo || null }),
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
  }, [dashboardId, reload, dateFrom, dateTo]);

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

  const applyOrder = async (order: string[]) => {
    try {
      await reorderComponents(dashboardId, order);
      load();
    } catch (cause) {
      setError(describeApiError(cause, 'Unable to reorder the tiles.'));
    }
  };

  const move = async (index: number, direction: -1 | 1) => {
    if (!detail) return;
    const order = detail.components.map(component => component.id);
    const target = index + direction;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    await applyOrder(order);
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id || !detail) return;
    const order = detail.components.map(component => component.id);
    const from = order.indexOf(String(active.id));
    const to = order.indexOf(String(over.id));
    if (from === -1 || to === -1) return;
    order.splice(to, 0, ...order.splice(from, 1));
    void applyOrder(order);
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
          <DateFilterBar
            dateFrom={dateFrom}
            dateTo={dateTo}
            onChange={(from, to) => {
              setDateFrom(from);
              setDateTo(to);
            }}
          />
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

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={tiles.map(tile => tile.id)} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            {tiles.map((tile, index) => (
              <DashboardTile
                key={tile.id}
                tile={tile}
                index={index}
                total={tiles.length}
                arranging={arranging}
                onMove={move}
                onRemove={dropTile}
                onChange={changeTile}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

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

/**
 * One tile, draggable while arranging (Checkpoint 5).
 *
 * The up/down buttons and the drag handle both exist at once and both call
 * the same `onMove`/drag-end path into `reorderComponents` — see the page
 * docstring for why neither is being deprecated in favour of the other.
 */
function DashboardTile({
  tile,
  index,
  total,
  arranging,
  onMove,
  onRemove,
  onChange,
}: {
  tile: DashboardComponentData;
  index: number;
  total: number;
  arranging: boolean;
  onMove: (index: number, direction: -1 | 1) => void;
  onRemove: (componentId: string, title: string) => void;
  onChange: (componentId: string, patch: { display?: ComponentDisplay; width?: number }) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: tile.id,
    disabled: !arranging,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'surface bd flex flex-col rounded-2xl border p-5',
        SPAN_CLASS[tile.width] ?? SPAN_CLASS[6],
        isDragging && 'z-10 opacity-60 shadow-xl',
      )}
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {arranging && (
            <button
              type="button"
              {...attributes}
              {...listeners}
              aria-label={`Drag to reorder ${tile.title}`}
              className="txt-faint hover:txt cursor-grab touch-none active:cursor-grabbing"
            >
              <GripVertical className="h-4 w-4" />
            </button>
          )}
          <h2 className="txt font-display truncate text-[14px] font-bold">{tile.title}</h2>
          {tile.date_filter_applied && (
            <span
              title="Narrowed by the dashboard's date filter"
              className="txt-faint inline-flex shrink-0 items-center gap-0.5 rounded-full border border-[var(--border)] px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wider"
            >
              <CalendarRange className="h-2.5 w-2.5" /> Filtered
            </span>
          )}
        </div>
        {arranging && (
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => onMove(index, -1)}
              disabled={index === 0}
              aria-label={`Move ${tile.title} earlier`}
              className="txt-faint hover:txt disabled:opacity-30"
            >
              <ChevronUp className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => onMove(index, 1)}
              disabled={index === total - 1}
              aria-label={`Move ${tile.title} later`}
              className="txt-faint hover:txt disabled:opacity-30"
            >
              <ChevronDown className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => onRemove(tile.id, tile.title)}
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
                onChange(tile.id, { display: event.target.value as ComponentDisplay })
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
              onChange={event => onChange(tile.id, { width: Number(event.target.value) })}
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
  );
}

/**
 * A dashboard-wide date range (Checkpoint 5).
 *
 * Narrows every tile whose underlying report has a date dimension — a
 * catalogue report with `accepts_date_range`, or any custom report, which
 * always has one — for this render only; nothing here is persisted. A tile
 * with no date dimension (most of the built-in catalogue) renders its usual
 * numbers unaffected, and says so via the "Filtered" badge's absence.
 */
function DateFilterBar({
  dateFrom,
  dateTo,
  onChange,
}: {
  dateFrom: string;
  dateTo: string;
  onChange: (dateFrom: string, dateTo: string) => void;
}) {
  const active = Boolean(dateFrom || dateTo);
  return (
    <div className="ctl bd flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px]">
      <CalendarRange className="h-3.5 w-3.5 txt-faint" aria-hidden="true" />
      <input
        type="date"
        aria-label="Dashboard filter: from date"
        value={dateFrom}
        onChange={event => onChange(event.target.value, dateTo)}
        className="txt bg-transparent text-[12px] outline-none"
      />
      <span className="txt-faint">–</span>
      <input
        type="date"
        aria-label="Dashboard filter: to date"
        value={dateTo}
        onChange={event => onChange(dateFrom, event.target.value)}
        className="txt bg-transparent text-[12px] outline-none"
      />
      {active && (
        <button
          type="button"
          onClick={() => onChange('', '')}
          aria-label="Clear dashboard date filter"
          className="txt-faint hover:text-rose-500"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
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
