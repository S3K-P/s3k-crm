import { apiRequest } from '@/lib/api-client';

/* ============================================================
   CSV IMPORT

   Bindings for `/crm/imports`. Two calls do the work and they
   are the same call twice: `preview` runs the import and throws
   the result away, `commit` keeps it. That is a backend
   guarantee, not a convention here — the wizard can therefore
   show the preview's numbers as a promise rather than an
   estimate.
   ============================================================ */

export type ImportEntitySlug = 'leads' | 'accounts' | 'contacts';

export type DuplicatePolicy = 'SKIP' | 'CREATE';

export interface ImportField {
  name: string;
  required: boolean;
}

export interface ImportEntityInfo {
  slug: ImportEntitySlug;
  label: string;
  fields: ImportField[];
  duplicate_field: string;
  max_rows: number;
}

export interface ImportRowIssue {
  row: number;
  field: string | null;
  message: string;
}

export interface ImportSummary {
  total_rows: number;
  created: number;
  skipped_duplicates: number;
  failed: number;
}

export interface ImportResult {
  dry_run: boolean;
  summary: ImportSummary;
  errors: ImportRowIssue[];
  duplicates: ImportRowIssue[];
  ignored_columns: string[];
}

export const listImportableEntities = () =>
  apiRequest<ImportEntityInfo[]>('/crm/imports/entities', { method: 'GET' });

/**
 * Run an import, or a dry run of one.
 *
 * The file is uploaded for each call. The API is stateless between preview and
 * commit by design, which removes any chance of committing a file other than
 * the one that was previewed.
 *
 * `Content-Type` is deliberately not set: the browser has to choose it so the
 * multipart boundary matches the body it generates.
 */
export async function runImport(
  slug: ImportEntitySlug,
  {
    file,
    mapping,
    duplicatePolicy,
    dryRun,
  }: {
    file: File;
    mapping: Record<string, string>;
    duplicatePolicy: DuplicatePolicy;
    dryRun: boolean;
  },
): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('mapping', JSON.stringify(mapping));
  form.append('duplicate_policy', duplicatePolicy);

  return apiRequest<ImportResult>(`/crm/imports/${slug}/${dryRun ? 'preview' : 'commit'}`, {
    method: 'POST',
    rawBody: form,
  });
}

/* ------------------------------------------------------------------
   Reading the header row
   ------------------------------------------------------------------ */

/**
 * Split one CSV line into fields, honouring quotes.
 *
 * Only the header is parsed in the browser, and only to populate the mapping
 * step — every value is parsed server-side by Python's `csv` module, which is
 * the one that decides what the file actually contains. Keeping this to a
 * single line is why it can stay this small: no embedded newlines to handle.
 */
export function parseCsvHeader(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  let quoted = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (quoted) {
      if (char === '"') {
        // A doubled quote inside a quoted field is one literal quote.
        if (line[index + 1] === '"') {
          current += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        current += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      fields.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  fields.push(current.trim());
  return fields;
}

/** Read the first line of a file, without loading the rest of it. */
export async function readCsvHeaders(file: File): Promise<string[]> {
  // 64 KB is far more than a header row and avoids pulling a multi-megabyte
  // file into memory just to read its first line.
  const head = await file.slice(0, 64 * 1024).text();
  const firstLine = head.split(/\r?\n/, 1)[0] ?? '';
  return parseCsvHeader(firstLine.replace(/^﻿/, ''));
}

/**
 * Guess a mapping from CSV headers to entity fields.
 *
 * Compared with punctuation and case removed, so `First Name`, `first_name`
 * and `FIRSTNAME` all find the same field. The common case — re-importing a
 * file this application exported — then needs no manual mapping at all, and
 * the importer's job becomes checking a guess rather than making thirty
 * choices.
 */
export function suggestMapping(
  headers: string[],
  fields: ImportField[],
): Record<string, string> {
  const normalise = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '');
  const byNormalised = new Map(fields.map((field) => [normalise(field.name), field.name]));

  const mapping: Record<string, string> = {};
  for (const header of headers) {
    if (!header) continue;
    const match = byNormalised.get(normalise(header));
    if (match) mapping[header] = match;
  }
  return mapping;
}

/* ------------------------------------------------------------------
   Blank import template
   ------------------------------------------------------------------ */

/** Quote a CSV field only when it has to be — a comma, quote or newline. */
function csvField(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/**
 * A blank CSV whose only row is the entity's importable column names, in
 * the order the API lists them. The headers are the exact field names, so
 * a user who fills this in and uploads it lands on the mapping step with
 * every column already paired up by `suggestMapping` and nothing to do
 * but confirm. Which columns are required is shown by the wizard itself.
 */
export function buildImportTemplateCsv(entity: ImportEntityInfo): string {
  const header = entity.fields.map((field) => csvField(field.name)).join(',');
  // Leading BOM so Excel opens it as UTF-8; `readCsvHeaders` strips it back off.
  return `﻿${header}\r\n`;
}

/** Build the blank template for an entity and save it to the user's disk. */
export function downloadImportTemplate(entity: ImportEntityInfo): string {
  const fileName = `${entity.slug}-import-template.csv`;
  const blob = new Blob([buildImportTemplateCsv(entity)], {
    type: 'text/csv;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
  return fileName;
}
