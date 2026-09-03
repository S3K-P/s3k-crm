'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  FileSpreadsheet,
  Loader2,
  Upload,
} from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import {
  notifyError,
  notifyErrorMessage,
  notifySuccess,
} from '@/components/crm/feedback/notify';
import {
  downloadImportTemplate,
  listImportableEntities,
  readCsvHeaders,
  runImport,
  suggestMapping,
  type DuplicatePolicy,
  type ImportEntityInfo,
  type ImportEntitySlug,
  type ImportResult,
  type ImportRowIssue,
} from '@/features/crm/imports';

/* ============================================================
   IMPORT WIZARD

   Four steps, and the third is the one that matters:

     upload → map → review (dry run) → done

   The review step is a real execution that was rolled back, so
   the numbers it shows are what the confirm step will do, not a
   forecast. That is why the confirm button can say "Import 42
   leads" rather than "Import".

   The wizard never decides what is valid. Every message shown
   here came from the API, which validated the rows with the
   same schema the normal create endpoint uses.
   ============================================================ */

type Step = 'upload' | 'map' | 'review' | 'done';

interface ImportWizardProps {
  open: boolean;
  onClose: () => void;
  slug: ImportEntitySlug;
  /** Called after a committed import so the list can refetch. */
  onImported: () => void;
}

const POLICY_LABELS: Record<DuplicatePolicy, string> = {
  SKIP: 'Skip them — keep the existing record',
  CREATE: 'Import them anyway — allow a duplicate',
};

function IssueTable({ issues, caption }: { issues: ImportRowIssue[]; caption: string }) {
  if (issues.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <h4 className="txt text-[13px] font-semibold">{caption}</h4>
      <div className="bd max-h-56 overflow-auto rounded-lg border">
        <table className="w-full text-[12.5px]">
          <thead className="surface-2 sticky top-0">
            <tr>
              <th className="txt-muted px-3 py-2 text-left font-semibold">Row</th>
              <th className="txt-muted px-3 py-2 text-left font-semibold">Column</th>
              <th className="txt-muted px-3 py-2 text-left font-semibold">Problem</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((issue, index) => (
              <tr key={`${issue.row}-${issue.field ?? ''}-${index}`} className="bd border-t">
                <td className="txt px-3 py-1.5 tabular-nums">{issue.row}</td>
                <td className="txt-muted px-3 py-1.5 font-mono text-[11.5px]">
                  {issue.field ?? '—'}
                </td>
                <td className="txt px-3 py-1.5">{issue.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ImportWizard({ open, onClose, slug, onImported }: ImportWizardProps) {
  const [entity, setEntity] = useState<ImportEntityInfo | null>(null);
  const [step, setStep] = useState<Step>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [policy, setPolicy] = useState<DuplicatePolicy>('SKIP');
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [outcome, setOutcome] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);

  /* The field list drives the mapping step; fetched once per open. */
  useEffect(() => {
    if (!open || entity) return;
    let cancelled = false;
    void (async () => {
      try {
        const entities = await listImportableEntities();
        const match = entities.find((candidate) => candidate.slug === slug);
        if (!cancelled && match) setEntity(match);
      } catch (error) {
        if (!cancelled) notifyError(error, 'Could not load the import settings.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, entity, slug]);

  const reset = useCallback(() => {
    setStep('upload');
    setFile(null);
    setHeaders([]);
    setMapping({});
    setPreview(null);
    setOutcome(null);
    setPolicy('SKIP');
  }, []);

  const close = useCallback(() => {
    onClose();
    reset();
  }, [onClose, reset]);

  const chooseFile = async (chosen: File) => {
    if (!entity) return;
    setBusy(true);
    try {
      const found = await readCsvHeaders(chosen);
      if (found.length === 0 || found.every((header) => !header)) {
        notifyErrorMessage('That file has no header row naming its columns.');
        return;
      }
      setFile(chosen);
      setHeaders(found);
      setMapping(suggestMapping(found, entity.fields));
      setStep('map');
    } catch {
      notifyErrorMessage('That file could not be read.');
    } finally {
      setBusy(false);
    }
  };

  const downloadTemplate = () => {
    if (!entity) return;
    const fileName = downloadImportTemplate(entity);
    notifySuccess('Template downloaded', fileName);
  };

  const run = async (dryRun: boolean) => {
    if (!file) return;
    setBusy(true);
    try {
      const result = await runImport(slug, {
        file,
        mapping,
        duplicatePolicy: policy,
        dryRun,
      });
      if (dryRun) {
        setPreview(result);
        setStep('review');
      } else {
        setOutcome(result);
        setStep('done');
        onImported();
      }
    } catch (error) {
      // The API's message names the reason — too many rows, not a CSV, no
      // permission — and is more useful than anything invented here.
      notifyError(error, 'The import could not be run.');
    } finally {
      setBusy(false);
    }
  };

  const missingRequired = (entity?.fields ?? [])
    .filter((field) => field.required)
    .filter((field) => !Object.values(mapping).includes(field.name))
    .map((field) => field.name);

  const label = entity?.label ?? 'record';
  const plural = `${label}s`;

  return (
    <SlideDrawer
      open={open}
      onClose={close}
      title={`Import ${plural}`}
      subtitle={
        entity ? `CSV, up to ${entity.max_rows.toLocaleString()} rows per file.` : 'Loading…'
      }
      width="max-w-2xl"
      footer={
        <>
          {step === 'map' && (
            <button
              type="button"
              onClick={() => setStep('upload')}
              className="ctl flex items-center gap-1.5 px-4 py-2.5 text-[13px] font-semibold transition hover:opacity-80"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
          )}
          {step === 'review' && (
            <button
              type="button"
              onClick={() => setStep('map')}
              className="ctl flex items-center gap-1.5 px-4 py-2.5 text-[13px] font-semibold transition hover:opacity-80"
            >
              <ArrowLeft className="h-4 w-4" /> Change mapping
            </button>
          )}
          <button
            type="button"
            onClick={close}
            className="ctl px-5 py-2.5 text-[13px] font-semibold transition hover:opacity-80"
          >
            {step === 'done' ? 'Close' : 'Cancel'}
          </button>
          {step === 'map' && (
            <button
              type="button"
              onClick={() => run(true)}
              disabled={busy || missingRequired.length > 0}
              className="flex items-center gap-2 rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {busy && <Loader2 className="h-4 w-4 motion-safe:animate-spin" />}
              Validate
            </button>
          )}
          {step === 'review' && preview && (
            <button
              type="button"
              onClick={() => run(false)}
              disabled={busy || preview.summary.created === 0}
              className="flex items-center gap-2 rounded-lg px-5 py-2.5 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {busy && <Loader2 className="h-4 w-4 motion-safe:animate-spin" />}
              Import {preview.summary.created} {preview.summary.created === 1 ? label : plural}
            </button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-5">
        {/* ---- Step 1: choose a file ---- */}
        {step === 'upload' && (
          <>
            <p className="txt-muted text-[13px]">
              Upload a CSV whose first row names the columns. You will be able to check how
              they map onto {label} fields, and see exactly what would happen, before anything
              is saved.
            </p>
            <label
              className="bd flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center transition hover:opacity-80"
              htmlFor="import-file"
            >
              {busy ? (
                <Loader2 className="txt-faint h-7 w-7 motion-safe:animate-spin" />
              ) : (
                <Upload className="txt-faint h-7 w-7" aria-hidden="true" />
              )}
              <span className="txt text-[13.5px] font-semibold">Choose a CSV file</span>
              <span className="txt-faint text-[12px]">
                Up to {entity?.max_rows.toLocaleString() ?? '5,000'} rows
              </span>
              <input
                id="import-file"
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                onChange={(event) => {
                  const chosen = event.target.files?.[0];
                  // Cleared so choosing the same file twice re-fires onChange.
                  event.target.value = '';
                  if (chosen) void chooseFile(chosen);
                }}
              />
            </label>
            <p className="txt-faint text-[12px]">
              Not sure of the format?{' '}
              <button
                type="button"
                onClick={downloadTemplate}
                disabled={!entity}
                className="txt font-semibold underline underline-offset-2 transition hover:opacity-80 disabled:opacity-50"
              >
                Download a blank CSV template
              </button>{' '}
              with a column for every {label} field.
            </p>
          </>
        )}

        {/* ---- Step 2: map the columns ---- */}
        {step === 'map' && entity && (
          <>
            <div className="txt-muted flex items-center gap-2 text-[13px]">
              <FileSpreadsheet className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="txt font-semibold">{file?.name}</span>
              <span>· {headers.length} columns</span>
            </div>

            <p className="txt-muted text-[13px]">
              Matching columns have been paired up for you. Set anything left as
              <span className="txt font-semibold"> Ignore </span>
              that should be imported.
            </p>

            <div className="flex flex-col gap-2">
              {headers.filter(Boolean).map((header) => (
                <div key={header} className="flex items-center gap-3">
                  <span className="txt w-1/2 truncate font-mono text-[12.5px]" title={header}>
                    {header}
                  </span>
                  <select
                    value={mapping[header] ?? ''}
                    aria-label={`Field for column ${header}`}
                    onChange={(event) => {
                      const field = event.target.value;
                      setMapping((previous) => {
                        const next = { ...previous };
                        if (field) next[header] = field;
                        else delete next[header];
                        return next;
                      });
                    }}
                    className="ctl w-1/2 px-3 py-2 text-[13px]"
                  >
                    <option value="">Ignore this column</option>
                    {entity.fields.map((field) => (
                      <option key={field.name} value={field.name}>
                        {field.name}
                        {field.required ? ' (required)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            {missingRequired.length > 0 && (
              <p
                className="flex items-start gap-2 text-[12.5px]"
                style={{ color: 'var(--danger, #dc2626)' }}
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  Map a column to {missingRequired.join(' and ')} before continuing — every{' '}
                  {label} needs {missingRequired.length === 1 ? 'it' : 'them'}.
                </span>
              </p>
            )}

            <div className="flex flex-col gap-2">
              <h4 className="txt text-[13px] font-semibold">
                If a row matches an existing {label} by {entity.duplicate_field}
              </h4>
              {(['SKIP', 'CREATE'] as DuplicatePolicy[]).map((option) => (
                <label key={option} className="txt-muted flex items-center gap-2 text-[13px]">
                  <input
                    type="radio"
                    name="duplicate-policy"
                    value={option}
                    checked={policy === option}
                    onChange={() => setPolicy(option)}
                  />
                  {POLICY_LABELS[option]}
                </label>
              ))}
            </div>
          </>
        )}

        {/* ---- Step 3: review the dry run ---- */}
        {step === 'review' && preview && (
          <>
            <div className="bd rounded-xl border p-4">
              <p className="txt-muted text-[12.5px]">
                Nothing has been saved yet. This is what importing this file would do.
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Rows in file" value={preview.summary.total_rows} />
                <Stat label="Will import" value={preview.summary.created} />
                <Stat label="Duplicates" value={preview.summary.skipped_duplicates} />
                <Stat label="Cannot import" value={preview.summary.failed} />
              </div>
            </div>

            {preview.ignored_columns.length > 0 && (
              <p className="txt-muted text-[12.5px]">
                Not imported: {preview.ignored_columns.join(', ')}.
              </p>
            )}

            <IssueTable issues={preview.errors} caption="Rows that cannot be imported" />
            <IssueTable
              issues={preview.duplicates}
              caption={
                policy === 'SKIP'
                  ? 'Rows that already exist and will be skipped'
                  : 'Rows that already exist and will be imported anyway'
              }
            />

            {preview.summary.created === 0 && (
              <p className="txt-muted text-[13px]">
                No rows can be imported as mapped. Go back and check the column mapping.
              </p>
            )}
          </>
        )}

        {/* ---- Step 4: the outcome ---- */}
        {step === 'done' && outcome && (
          <>
            <div className="flex items-start gap-3">
              {outcome.summary.failed === 0 ? (
                <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0" style={{ color: '#059669' }} />
              ) : (
                <AlertTriangle
                  className="mt-0.5 h-6 w-6 shrink-0"
                  style={{ color: '#d97706' }}
                />
              )}
              <div>
                <h3 className="txt text-[15px] font-semibold">
                  Imported {outcome.summary.created}{' '}
                  {outcome.summary.created === 1 ? label : plural}
                </h3>
                <p className="txt-muted mt-0.5 text-[13px]">
                  {outcome.summary.skipped_duplicates > 0 &&
                    `${outcome.summary.skipped_duplicates} skipped as duplicates. `}
                  {outcome.summary.failed > 0
                    ? `${outcome.summary.failed} could not be imported and were not saved.`
                    : 'Every row was imported.'}
                </p>
              </div>
            </div>

            <IssueTable issues={outcome.errors} caption="Rows that were not imported" />

            {outcome.summary.failed > 0 && (
              <p className="txt-muted text-[12.5px]">
                Nothing else was affected — the rows above were rejected individually, and the
                rest of the file was imported.
              </p>
            )}
          </>
        )}
      </div>
    </SlideDrawer>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="txt-faint text-[11px] font-semibold uppercase tracking-wide">{label}</p>
      <p className="txt mt-0.5 text-[19px] font-bold tabular-nums">{value}</p>
    </div>
  );
}
