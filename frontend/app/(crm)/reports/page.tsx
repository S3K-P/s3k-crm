'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  CalendarRange,
  FolderPlus,
  Lock,
  Pencil,
  RefreshCw,
  Save,
  Trash2,
  Users,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { ListEmpty, ListError } from '@/components/crm/shared/ListStates';
import {
  ReportChart,
  ReportTable,
  chartHasData,
} from '@/components/crm/reports/ReportView';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  byCategory,
  listReports,
  runReport,
  type ReportResult,
  type ReportSummary,
} from '@/features/crm/reports';
import {
  REPORT_PERIODS,
  createFolder,
  createSavedReport,
  deleteFolder,
  deleteSavedReport,
  listFolders,
  listSavedReports,
  periodLabel,
  runSavedReport,
  updateSavedReport,
  type ReportFolder,
  type ReportPeriod,
  type SavedReport,
  type ShareScope,
} from '@/features/crm/reports/library';

/* ============================================================
   REPORTS

   The catalogue and the saved library share one screen, because
   they are two views of the same thing: a saved report *is* a
   catalogue entry plus a period and a name. Selecting either
   runs a report and draws it the same way.

   The screen knows nothing about any individual report. A result
   describes its own columns, so a report added to the backend
   catalogue appears here — table, chart and totals — with no
   change to this file.
   ============================================================ */

/** What the right-hand pane is currently showing. */
type Selection =
  | { kind: 'catalogue'; key: string }
  | { kind: 'saved'; id: string };

const EMPTY_FORM = {
  name: '',
  description: '',
  folder_id: '',
  period: 'ALL_TIME' as ReportPeriod,
  date_from: '',
  date_to: '',
  visibility: 'PRIVATE' as ShareScope,
};

type SaveForm = typeof EMPTY_FORM;

export default function ReportsPage() {
  const confirm = useConfirm();

  const [catalogue, setCatalogue] = useState<ReportSummary[] | null>(null);
  const [folders, setFolders] = useState<ReportFolder[]>([]);
  const [saved, setSaved] = useState<SavedReport[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selection, setSelection] = useState<Selection | null>(null);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const [drawer, setDrawer] = useState<'save' | 'edit' | 'folder' | null>(null);
  const [form, setForm] = useState<SaveForm>(EMPTY_FORM);
  const [folderName, setFolderName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const activeCatalogue = useMemo(
    () =>
      selection?.kind === 'catalogue'
        ? (catalogue?.find(report => report.key === selection.key) ?? null)
        : null,
    [selection, catalogue],
  );
  const activeSaved = useMemo(
    () =>
      selection?.kind === 'saved'
        ? (saved.find(report => report.id === selection.id) ?? null)
        : null,
    [selection, saved],
  );

  /**
   * Whether the report being saved or edited actually reads a date range.
   *
   * Resolved against the catalogue for both modes: a saved report knows its
   * base key, and the catalogue is the only thing that knows whether that key
   * takes a window.
   */
  const periodApplies = useMemo(() => {
    const key =
      drawer === 'edit' ? activeSaved?.base_report_key : activeCatalogue?.key;
    return catalogue?.find(report => report.key === key)?.accepts_date_range ?? false;
  }, [drawer, activeSaved, activeCatalogue, catalogue]);

  /** The same question for whatever saved report is on screen. */
  const savedTakesPeriod = useMemo(
    () =>
      catalogue?.find(report => report.key === activeSaved?.base_report_key)
        ?.accepts_date_range ?? false,
    [activeSaved, catalogue],
  );

  /* --- Loading ------------------------------------------------------- */

  const loadLibrary = useCallback(async () => {
    const [folderPage, savedPage] = await Promise.all([
      listFolders(),
      listSavedReports(),
    ]);
    setFolders(folderPage.data);
    setSaved(savedPage.data);
  }, []);

  const runCatalogue = useCallback(async (key: string, from: string, to: string) => {
    setRunning(true);
    try {
      setResult(await runReport(key, { date_from: from || null, date_to: to || null }));
      setRunError(null);
    } catch (cause) {
      setResult(null);
      setRunError(describeApiError(cause, 'Unable to run this report right now.'));
    } finally {
      setRunning(false);
    }
  }, []);

  const runSaved = useCallback(async (id: string) => {
    setRunning(true);
    try {
      setResult(await runSavedReport(id));
      setRunError(null);
    } catch (cause) {
      setResult(null);
      setRunError(describeApiError(cause, 'Unable to run this report right now.'));
    } finally {
      setRunning(false);
    }
  }, []);

  // Open with something on screen rather than an instruction to pick.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const reports = await listReports();
        if (cancelled) return;
        setCatalogue(reports);
        setLoadError(null);
        await loadLibrary();
        if (cancelled) return;
        if (reports.length > 0) {
          setSelection({ kind: 'catalogue', key: reports[0].key });
          await runCatalogue(reports[0].key, '', '');
        }
      } catch (cause) {
        if (!cancelled) setLoadError(describeApiError(cause, 'Unable to load reports.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadLibrary, runCatalogue]);

  /* --- Selection ----------------------------------------------------- */

  const chooseCatalogue = (key: string) => {
    setSelection({ kind: 'catalogue', key });
    setDateFrom('');
    setDateTo('');
    void runCatalogue(key, '', '');
  };

  const chooseSaved = (id: string) => {
    setSelection({ kind: 'saved', id });
    void runSaved(id);
  };

  const rerun = () => {
    if (selection?.kind === 'saved') void runSaved(selection.id);
    else if (selection?.kind === 'catalogue') {
      void runCatalogue(selection.key, dateFrom, dateTo);
    }
  };

  /* --- Saving -------------------------------------------------------- */

  const openSaveDrawer = () => {
    if (!activeCatalogue) return;
    setForm({
      ...EMPTY_FORM,
      name: activeCatalogue.name,
      // Carry the dates the user is already looking at into the saved
      // definition, so "save this" saves what is on screen.
      period: dateFrom || dateTo ? 'CUSTOM' : 'ALL_TIME',
      date_from: dateFrom,
      date_to: dateTo,
    });
    setFormError(null);
    setDrawer('save');
  };

  const openEditDrawer = () => {
    if (!activeSaved) return;
    setForm({
      name: activeSaved.name,
      description: activeSaved.description ?? '',
      folder_id: activeSaved.folder_id ?? '',
      period: activeSaved.period,
      date_from: activeSaved.date_from ?? '',
      date_to: activeSaved.date_to ?? '',
      visibility: activeSaved.visibility,
    });
    setFormError(null);
    setDrawer('edit');
  };

  const submitSave = async () => {
    setBusy(true);
    setFormError(null);
    try {
      // A report that ignores dates is stored as ALL_TIME whatever the form
      // last held, so its stored period never claims a window it does not use.
      const period = periodApplies ? form.period : 'ALL_TIME';
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        folder_id: form.folder_id || null,
        period,
        date_from: period === 'CUSTOM' ? form.date_from || null : null,
        date_to: period === 'CUSTOM' ? form.date_to || null : null,
        visibility: form.visibility,
      };

      if (drawer === 'edit' && activeSaved) {
        await updateSavedReport(activeSaved.id, payload);
        await loadLibrary();
        setDrawer(null);
        void runSaved(activeSaved.id);
      } else if (activeCatalogue) {
        const created = await createSavedReport({
          ...payload,
          base_report_key: activeCatalogue.key,
        });
        await loadLibrary();
        setDrawer(null);
        setSelection({ kind: 'saved', id: created.id });
        void runSaved(created.id);
      }
    } catch (cause) {
      setFormError(describeApiError(cause, 'Unable to save this report.'));
    } finally {
      setBusy(false);
    }
  };

  const submitFolder = async () => {
    setBusy(true);
    setFormError(null);
    try {
      await createFolder({ name: folderName.trim() });
      setFolderName('');
      setDrawer(null);
      await loadLibrary();
    } catch (cause) {
      setFormError(describeApiError(cause, 'Unable to create this folder.'));
    } finally {
      setBusy(false);
    }
  };

  const removeSaved = async () => {
    if (!activeSaved) return;
    const answer = await confirm({
      title: `Delete “${activeSaved.name}”?`,
      description: 'The report definition is archived. No records are affected.',
      confirmLabel: 'Delete',
      tone: 'danger',
    });
    if (!answer) return;
    try {
      await deleteSavedReport(activeSaved.id);
      await loadLibrary();
      setSelection(
        catalogue && catalogue.length > 0
          ? { kind: 'catalogue', key: catalogue[0].key }
          : null,
      );
      if (catalogue && catalogue.length > 0) {
        void runCatalogue(catalogue[0].key, '', '');
      } else {
        setResult(null);
      }
    } catch (cause) {
      setRunError(describeApiError(cause, 'Unable to delete this report.'));
    }
  };

  const removeFolder = async (folder: ReportFolder) => {
    const answer = await confirm({
      title: `Delete “${folder.name}”?`,
      description: 'Only empty folders can be deleted.',
      confirmLabel: 'Delete',
      tone: 'danger',
    });
    if (!answer) return;
    try {
      await deleteFolder(folder.id);
      await loadLibrary();
    } catch (cause) {
      setLoadError(describeApiError(cause, 'Unable to delete this folder.'));
    }
  };

  /* --- Render -------------------------------------------------------- */

  const unfiled = saved.filter(report => report.folder_id === null);
  const activeName = activeSaved?.name ?? activeCatalogue?.name ?? '';
  const activeDescription =
    activeSaved?.description ?? activeCatalogue?.description ?? '';

  return (
    <div className="flex h-full flex-col space-y-5 p-4 sm:p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
          <BarChart3 className="h-5 w-5 text-white" />
        </div>
        <div className="min-w-0">
          <h1 className="font-display txt text-[22px] font-extrabold leading-tight tracking-tight">
            Reports
          </h1>
          <p className="txt-muted mt-0.5 text-[13px] font-medium">
            Every report counts only the records you can open.
          </p>
        </div>
      </div>

      {loadError && (
        <ListError message={loadError} onRetry={() => window.location.reload()} />
      )}

      {catalogue?.length === 0 && saved.length === 0 && (
        <ListEmpty
          title="No reports available"
          hint="Reports follow the records you can see. Ask an administrator for access to leads, deals or accounts."
        />
      )}

      <div className="grid flex-1 gap-6 lg:grid-cols-[260px_1fr]">
        {/* Library */}
        <nav className="space-y-5" aria-label="Reports">
          {saved.length > 0 && (
            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wider">
                  Saved
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setFolderName('');
                    setFormError(null);
                    setDrawer('folder');
                  }}
                  className="txt-faint hover:txt inline-flex items-center gap-1 text-[11px] font-semibold"
                >
                  <FolderPlus className="h-3 w-3" /> Folder
                </button>
              </div>

              {folders.map(folder => {
                const inFolder = saved.filter(report => report.folder_id === folder.id);
                return (
                  <div key={folder.id} className="mb-3">
                    <div className="group flex items-center justify-between px-1">
                      <p className="txt-muted truncate text-[11.5px] font-semibold">
                        {folder.name}
                      </p>
                      {inFolder.length === 0 && (
                        <button
                          type="button"
                          onClick={() => void removeFolder(folder)}
                          aria-label={`Delete folder ${folder.name}`}
                          className="txt-faint opacity-0 transition group-hover:opacity-100 hover:text-rose-500"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                    <SavedList
                      reports={inFolder}
                      selectedId={activeSaved?.id}
                      onSelect={chooseSaved}
                    />
                  </div>
                );
              })}

              {unfiled.length > 0 && (
                <div className="mb-3">
                  {folders.length > 0 && (
                    <p className="txt-muted px-1 text-[11.5px] font-semibold">Unfiled</p>
                  )}
                  <SavedList
                    reports={unfiled}
                    selectedId={activeSaved?.id}
                    onSelect={chooseSaved}
                  />
                </div>
              )}
            </div>
          )}

          {catalogue &&
            byCategory(catalogue).map(([category, reports]) => (
              <div key={category}>
                <p className="txt-faint mb-2 text-[10.5px] font-bold uppercase tracking-wider">
                  {category}
                </p>
                <div className="space-y-1">
                  {reports.map(report => (
                    <button
                      key={report.key}
                      type="button"
                      onClick={() => chooseCatalogue(report.key)}
                      aria-current={
                        activeCatalogue?.key === report.key ? 'true' : undefined
                      }
                      className={cn(
                        'w-full rounded-lg px-3 py-2 text-left text-[12.5px] font-medium transition-colors',
                        activeCatalogue?.key === report.key
                          ? 'bg-[var(--accent-soft)] text-[var(--accent)]'
                          : 'txt-muted hover:surface-2',
                      )}
                    >
                      {report.name}
                    </button>
                  ))}
                </div>
              </div>
            ))}
        </nav>

        {/* Selected report */}
        <div className="min-w-0 space-y-5">
          {selection && (
            <div className="surface bd flex flex-col gap-3 rounded-2xl border p-4 lg:flex-row lg:items-end lg:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="txt font-display truncate text-[16px] font-bold">
                    {activeName}
                  </h2>
                  {activeSaved && (
                    <span
                      title={
                        activeSaved.visibility === 'SHARED'
                          ? 'Shared with the organization'
                          : 'Only you can see this'
                      }
                      className="txt-faint inline-flex items-center gap-1 rounded-full border border-[var(--border)] px-2 py-0.5 text-[10.5px] font-semibold"
                    >
                      {activeSaved.visibility === 'SHARED' ? (
                        <Users className="h-3 w-3" />
                      ) : (
                        <Lock className="h-3 w-3" />
                      )}
                      {activeSaved.visibility === 'SHARED' ? 'Shared' : 'Private'}
                    </span>
                  )}
                </div>
                <p className="txt-muted text-[12.5px]">{activeDescription}</p>
                {activeSaved && savedTakesPeriod && (
                  <p className="txt-faint mt-0.5 text-[11.5px]">
                    {periodLabel(activeSaved.period)}
                    {activeSaved.period === 'CUSTOM' &&
                      ` · ${activeSaved.date_from ?? '…'} to ${activeSaved.date_to ?? '…'}`}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap items-end gap-2">
                {activeCatalogue?.accepts_date_range && (
                  <>
                    <label className="txt-faint flex flex-col gap-1 text-[10.5px] font-bold uppercase tracking-wider">
                      <span className="flex items-center gap-1">
                        <CalendarRange className="h-3 w-3" /> From
                      </span>
                      <input
                        type="date"
                        value={dateFrom}
                        onChange={event => setDateFrom(event.target.value)}
                        className="ctl txt px-2.5 py-1.5 text-[12.5px] font-normal normal-case tracking-normal"
                      />
                    </label>
                    <label className="txt-faint flex flex-col gap-1 text-[10.5px] font-bold uppercase tracking-wider">
                      To
                      <input
                        type="date"
                        value={dateTo}
                        onChange={event => setDateTo(event.target.value)}
                        className="ctl txt px-2.5 py-1.5 text-[12.5px] font-normal normal-case tracking-normal"
                      />
                    </label>
                  </>
                )}

                {activeCatalogue && (
                  <button
                    type="button"
                    onClick={openSaveDrawer}
                    className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
                  >
                    <Save className="h-3.5 w-3.5" /> Save
                  </button>
                )}
                {activeSaved && (
                  <>
                    <button
                      type="button"
                      onClick={openEditDrawer}
                      className="ctl bd inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:opacity-80"
                    >
                      <Pencil className="h-3.5 w-3.5" /> Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => void removeSaved()}
                      aria-label={`Delete ${activeSaved.name}`}
                      className="ctl bd inline-flex items-center rounded-lg border px-3 py-2 text-[12.5px] font-semibold transition hover:text-rose-500"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}

                <button
                  type="button"
                  disabled={running}
                  onClick={rerun}
                  className="flex items-center gap-2 rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
                  style={{ background: 'var(--accent)' }}
                >
                  <RefreshCw className={cn('h-3.5 w-3.5', running && 'animate-spin')} />
                  {running ? 'Running…' : 'Run'}
                </button>
              </div>
            </div>
          )}

          {runError && <ListError message={runError} onRetry={rerun} />}

          {result && (
            <>
              {result.row_limit_reached && (
                <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3.5 py-2.5 text-[12.5px] text-amber-700 dark:text-amber-400">
                  This report hit its row limit. Narrow the period to see the whole picture.
                </p>
              )}
              {/* `chartHasData` rather than a row count: a report with rows
                  whose values are all zero draws nothing, and the bordered
                  box would be left empty above the table. */}
              {chartHasData(result) && (
                <div className="surface bd rounded-2xl border p-5">
                  <ReportChart result={result} />
                </div>
              )}
              <div className="surface bd overflow-hidden rounded-2xl border">
                <ReportTable result={result} />
              </div>
              <p className="txt-faint text-[11.5px]">
                Generated {new Date(result.generated_at).toLocaleString()}
              </p>
            </>
          )}
        </div>
      </div>

      {/* Save / edit */}
      <SlideDrawer
        open={drawer === 'save' || drawer === 'edit'}
        onClose={() => setDrawer(null)}
        title={drawer === 'edit' ? 'Edit saved report' : 'Save report'}
        subtitle={
          drawer === 'edit'
            ? undefined
            : 'Saves the question, not the answer — it runs fresh every time.'
        }
        footer={
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setDrawer(null)}
              className="ctl bd rounded-lg border px-4 py-2 text-[12.5px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || !form.name.trim()}
              onClick={() => void submitSave()}
              className="rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {busy ? 'Saving…' : 'Save'}
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
          <Field label="Name">
            <input
              value={form.name}
              onChange={event => setForm({ ...form, name: event.target.value })}
              className="ctl txt w-full px-3 py-2 text-[13px]"
              maxLength={120}
            />
          </Field>
          <Field label="Description">
            <textarea
              value={form.description}
              onChange={event => setForm({ ...form, description: event.target.value })}
              rows={2}
              className="ctl txt w-full px-3 py-2 text-[13px]"
            />
          </Field>
          <Field label="Folder">
            <select
              value={form.folder_id}
              onChange={event => setForm({ ...form, folder_id: event.target.value })}
              className="ctl txt w-full px-3 py-2 text-[13px]"
            >
              <option value="">No folder</option>
              {folders.map(folder => (
                <option key={folder.id} value={folder.id}>
                  {folder.name}
                </option>
              ))}
            </select>
          </Field>
          {/* A report that ignores dates gets no period picker. Offering one
              would be a control that silently does nothing — the backend
              discards the window for a definition whose `accepts_date_range`
              is false, and a saved "This quarter" that means all time is
              worse than no choice at all. */}
          {periodApplies ? (
            <Field label="Period">
              <select
                value={form.period}
                onChange={event =>
                  setForm({ ...form, period: event.target.value as ReportPeriod })
                }
                className="ctl txt w-full px-3 py-2 text-[13px]"
              >
                {REPORT_PERIODS.map(period => (
                  <option key={period.value} value={period.value}>
                    {period.label}
                  </option>
                ))}
              </select>
            </Field>
          ) : (
            <p className="txt-faint text-[11.5px]">
              This report always covers everything current — it has no period to set.
            </p>
          )}
          {periodApplies && form.period === 'CUSTOM' && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="From">
                <input
                  type="date"
                  value={form.date_from}
                  onChange={event => setForm({ ...form, date_from: event.target.value })}
                  className="ctl txt w-full px-3 py-2 text-[13px]"
                />
              </Field>
              <Field label="To">
                <input
                  type="date"
                  value={form.date_to}
                  onChange={event => setForm({ ...form, date_to: event.target.value })}
                  className="ctl txt w-full px-3 py-2 text-[13px]"
                />
              </Field>
            </div>
          )}
          <Field label="Visibility">
            <select
              value={form.visibility}
              onChange={event =>
                setForm({ ...form, visibility: event.target.value as ShareScope })
              }
              className="ctl txt w-full px-3 py-2 text-[13px]"
            >
              <option value="PRIVATE">Private — only you</option>
              <option value="SHARED">Shared — everyone in the organization</option>
            </select>
            <p className="txt-faint mt-1 text-[11.5px]">
              Colleagues who open a shared report still see only their own records.
            </p>
          </Field>
        </div>
      </SlideDrawer>

      {/* New folder */}
      <SlideDrawer
        open={drawer === 'folder'}
        onClose={() => setDrawer(null)}
        title="New folder"
        footer={
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setDrawer(null)}
              className="ctl bd rounded-lg border px-4 py-2 text-[12.5px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || !folderName.trim()}
              onClick={() => void submitFolder()}
              className="rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {busy ? 'Creating…' : 'Create'}
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
          <Field label="Name">
            <input
              value={folderName}
              onChange={event => setFolderName(event.target.value)}
              className="ctl txt w-full px-3 py-2 text-[13px]"
              maxLength={120}
            />
          </Field>
          <p className="txt-faint text-[11.5px]">
            Folders are shared with the organization. What each report inside shows
            still depends on who opens it.
          </p>
        </div>
      </SlideDrawer>
    </div>
  );
}

function SavedList({
  reports,
  selectedId,
  onSelect,
}: {
  reports: SavedReport[];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="mt-1 space-y-1">
      {reports.map(report => (
        <button
          key={report.id}
          type="button"
          onClick={() => onSelect(report.id)}
          aria-current={report.id === selectedId ? 'true' : undefined}
          className={cn(
            'flex w-full items-center gap-1.5 rounded-lg px-3 py-2 text-left text-[12.5px] font-medium transition-colors',
            report.id === selectedId
              ? 'bg-[var(--accent-soft)] text-[var(--accent)]'
              : 'txt-muted hover:surface-2',
          )}
        >
          {report.visibility === 'SHARED' ? (
            <Users className="h-3 w-3 shrink-0" />
          ) : (
            <Lock className="h-3 w-3 shrink-0" />
          )}
          <span className="truncate">{report.name}</span>
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
        {label}
      </span>
      {children}
    </label>
  );
}
