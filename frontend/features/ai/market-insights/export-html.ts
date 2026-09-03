/**
 * The Market Intelligence Report as a standalone HTML document.
 *
 * The report is generated, read and stored as Markdown — that is the contract
 * the prompt, the parser and the on-screen renderer all share. This module is
 * the one place that turns it into a document somebody can send: a single
 * self-contained file with its CSS embedded, no scripts, no network requests,
 * and a print stylesheet so the same file saves as a two-to-three page PDF.
 *
 * **Nothing here interpolates model output as markup.** The Markdown is parsed
 * into the same block tree the screen renders, and every text node goes
 * through `escapeHtml` on its way into the string. Model output is untrusted
 * text; it never becomes an element, an attribute or a URL that was not first
 * escaped, and hrefs were already filtered to http(s) at parse time. That is
 * the same rule `MarkdownContent` follows, restated for a target where React
 * is not doing the escaping for us.
 *
 * The layout follows the brief the prompt asks for: an executive summary box
 * at the top, key insights called out in the accent colour, grey section
 * cards, tables where the model wrote them, and the retrieved sources listed
 * at the end.
 */

import { parseReport, type Block, type InlineNode } from '@/features/ai/market-insights/markdown';
import {
  asHtmlDocument,
  looksLikeHtmlDocument,
  unfence,
} from '@/features/ai/market-insights/html-report';
import type { ResearchSource } from '@/features/ai/market-insights';

/* ------------------------------------------------------------------
   Escaping
   ------------------------------------------------------------------ */

const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

/** Escape for both text and attribute contexts. */
function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ESCAPES[character]);
}

/* ------------------------------------------------------------------
   Markdown → HTML
   ------------------------------------------------------------------ */

function renderInline(nodes: InlineNode[]): string {
  return nodes
    .map((node) => {
      switch (node.kind) {
        case 'strong':
          return `<strong>${escapeHtml(node.text)}</strong>`;
        case 'em':
          return `<em>${escapeHtml(node.text)}</em>`;
        case 'code':
          return `<code>${escapeHtml(node.text)}</code>`;
        case 'link':
          return `<a href="${escapeHtml(node.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(node.text)}</a>`;
        default:
          return escapeHtml(node.text);
      }
    })
    .join('');
}

function renderBlock(block: Block): string {
  switch (block.kind) {
    case 'heading':
      return `<h${block.level}>${renderInline(block.content)}</h${block.level}>`;

    case 'list': {
      const tag = block.ordered ? 'ol' : 'ul';
      const items = block.items.map((item) => `<li>${renderInline(item)}</li>`).join('');
      return `<${tag}>${items}</${tag}>`;
    }

    case 'quote':
      return `<blockquote>${renderInline(block.content)}</blockquote>`;

    case 'table': {
      const head = block.headers
        .map(
          (header, column) =>
            `<th style="text-align:${block.align[column]}">${renderInline(header)}</th>`,
        )
        .join('');
      const body = block.rows
        .map((row) => {
          const cells = row
            .map(
              (cell, column) =>
                `<td style="text-align:${block.align[column]}">${renderInline(cell)}</td>`,
            )
            .join('');
          return `<tr>${cells}</tr>`;
        })
        .join('');
      return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    }

    default:
      return `<p>${renderInline(block.content)}</p>`;
  }
}

const renderBlocks = (blocks: Block[]): string => blocks.map(renderBlock).join('\n');

/* ------------------------------------------------------------------
   Document assembly
   ------------------------------------------------------------------ */

/** Sections the document lays out itself rather than as an ordinary card. */
const EXECUTIVE_SUMMARY = /^executive summary$/i;
const KEY_INSIGHTS = /^key insights?$/i;

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  // Spelt-out month: this file gets emailed, and 03/09/2026 means two
  // different days depending on who opens it.
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function sourceHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

const STYLES = `
  :root {
    --ink: #0b1f3a;
    --body: #1f2937;
    --muted: #5b6b7f;
    --accent: #1a56db;
    --accent-soft: #eef3fd;
    --card: #f7f9fb;
    --border: #e3e8ef;
  }
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    margin: 0;
    padding: 32px 20px 56px;
    background: #ffffff;
    color: var(--body);
    font: 400 13.5px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      "Helvetica Neue", Arial, sans-serif;
    font-feature-settings: "kern" 1;
  }
  .sheet { max-width: 860px; margin: 0 auto; }

  /* --- Masthead --- */
  .masthead { border-bottom: 3px solid var(--ink); padding-bottom: 14px; }
  .eyebrow {
    margin: 0;
    color: var(--accent);
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .masthead h1 {
    margin: 6px 0 0;
    color: var(--ink);
    font-size: 27px;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.15;
  }
  .meta {
    margin: 8px 0 0;
    color: var(--muted);
    font-size: 11.5px;
  }
  .meta span + span::before { content: " · "; }

  /* --- Callouts --- */
  .summary {
    margin: 20px 0 0;
    padding: 16px 18px;
    border: 1px solid var(--border);
    border-left: 4px solid var(--ink);
    border-radius: 8px;
    background: var(--card);
  }
  .insights {
    margin: 14px 0 0;
    padding: 16px 18px;
    border: 1px solid #d7e3fb;
    border-left: 4px solid var(--accent);
    border-radius: 8px;
    background: var(--accent-soft);
  }
  .callout-title {
    margin: 0 0 8px;
    color: var(--ink);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .insights .callout-title { color: var(--accent); }

  /* --- Section cards --- */
  .section {
    margin: 14px 0 0;
    padding: 15px 18px 17px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--card);
  }
  .section > h2 {
    margin: 0 0 9px;
    padding-bottom: 7px;
    border-bottom: 1px solid var(--border);
    color: var(--ink);
    font-size: 14.5px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  /* --- Prose --- */
  h3, h4 { margin: 13px 0 5px; color: var(--ink); font-weight: 700; }
  h3 { font-size: 12.8px; }
  h4 { font-size: 12.2px; }
  p { margin: 0 0 8px; }
  ul, ol { margin: 0 0 8px; padding-left: 19px; }
  li { margin: 0 0 4px; }
  blockquote {
    margin: 0 0 8px;
    padding-left: 11px;
    border-left: 3px solid var(--accent);
    color: var(--muted);
    font-style: italic;
  }
  code {
    padding: 1px 4px;
    border-radius: 3px;
    background: #eef1f5;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11.5px;
  }
  a { color: var(--accent); text-decoration: underline; text-underline-offset: 2px; }
  strong { color: var(--ink); font-weight: 650; }

  /* --- Tables --- */
  .table-wrap { margin: 0 0 10px; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td {
    padding: 6px 9px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  th {
    background: #edf1f6;
    color: var(--ink);
    font-weight: 650;
    white-space: nowrap;
  }
  tbody tr:last-child td { border-bottom: 0; }

  /* --- Sources --- */
  .sources { margin: 18px 0 0; padding-top: 14px; border-top: 2px solid var(--ink); }
  .sources h2 { margin: 0 0 4px; color: var(--ink); font-size: 14.5px; font-weight: 700; }
  .sources p.lede { margin: 0 0 10px; color: var(--muted); font-size: 11.5px; }
  .sources ol { padding-left: 20px; }
  .sources li { margin: 0 0 7px; }
  .sources .where { display: block; color: var(--muted); font-size: 11px; }
  .badge {
    display: inline-block;
    margin-left: 6px;
    padding: 0 5px;
    border-radius: 3px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    vertical-align: 1px;
  }

  footer {
    margin: 22px 0 0;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: 10.5px;
    line-height: 1.5;
  }

  @media print {
    @page { size: A4; margin: 14mm; }
    body { padding: 0; font-size: 10.5pt; }
    .sheet { max-width: none; }
    /* Keep the short, self-contained things whole. Section cards are left to
       break: a report of a dozen cards each forbidden to split leaves a page
       half empty every time one does not fit. What must not happen is a
       heading stranded at the foot of a page, hence break-after on the h2
       and the widow and orphan floors on the prose. */
    .summary, .insights, .table-wrap, tr { break-inside: avoid; }
    .section > h2, h3, h4 { break-after: avoid; }
    p, li { orphans: 2; widows: 2; }
    a { color: var(--accent); }
  }
`;

export interface ReportDocument {
  companyName: string;
  /** The report body, as the model wrote it. */
  markdown: string;
  /** Pages the research actually retrieved. */
  sources: ResearchSource[];
  /** When the research ran, ISO-8601. */
  generatedAt: string;
  model: string | null;
  promptVersion: number | null;
  usedCrmContext: boolean;
}

/**
 * Build the complete `.html` file for one report.
 *
 * Returns a full document string, ready to be saved as a Blob or written into
 * an iframe for printing.
 */
export function buildReportHtml(report: ReportDocument): string {
  // The model may already have written a complete HTML document, if that is
  // what the configured prompt asked for. Wrapping that in this template would
  // produce a page inside a page; the right export is the file it wrote.
  const content = unfence(report.markdown);
  if (looksLikeHtmlDocument(content)) return asHtmlDocument(content);

  const sections = parseReport(content);

  const lead = sections.find((section) => section.title === '');
  const summary = sections.find((section) => EXECUTIVE_SUMMARY.test(section.title));
  const insights = sections.find((section) => KEY_INSIGHTS.test(section.title));

  const cards = sections.filter(
    (section) => section.title !== '' && section !== summary && section !== insights,
  );

  const meta = [
    `Market research report · ${escapeHtml(formatDate(report.generatedAt))}`,
    report.usedCrmContext ? 'Includes CRM context' : null,
    report.promptVersion !== null ? `Prompt v${report.promptVersion}` : null,
    report.model ? escapeHtml(report.model) : null,
  ]
    .filter((entry): entry is string => Boolean(entry))
    .map((entry) => `<span>${entry}</span>`)
    .join('');

  const parts: string[] = [
    '<header class="masthead">',
    '<p class="eyebrow">Market Intelligence</p>',
    `<h1>${escapeHtml(report.companyName)}</h1>`,
    `<p class="meta">${meta}</p>`,
    '</header>',
  ];

  // Anything the model wrote before its first heading introduces the report
  // rather than being a section of it, so it sits above the summary box.
  if (lead && lead.blocks.length > 0) {
    parts.push(`<div class="lead">${renderBlocks(lead.blocks)}</div>`);
  }

  if (summary) {
    parts.push(
      '<section class="summary">',
      `<p class="callout-title">${escapeHtml(summary.title)}</p>`,
      renderBlocks(summary.blocks),
      '</section>',
    );
  }

  if (insights) {
    parts.push(
      '<section class="insights">',
      `<p class="callout-title">${escapeHtml(insights.title)}</p>`,
      renderBlocks(insights.blocks),
      '</section>',
    );
  }

  // A report with no headings at all is unusual but not an error — the prompt
  // may have been edited to ask for none. Show the prose rather than a page
  // with only a masthead on it.
  if (cards.length === 0 && !summary && !insights && !lead) {
    parts.push(
      `<section class="section">${renderBlocks(sections.flatMap((section) => section.blocks))}</section>`,
    );
  }

  for (const section of cards) {
    parts.push(
      '<section class="section">',
      `<h2>${escapeHtml(section.title)}</h2>`,
      renderBlocks(section.blocks),
      '</section>',
    );
  }

  if (report.sources.length > 0) {
    const items = report.sources
      .map((source) => {
        const cited = source.cited ? '<span class="badge">Cited</span>' : '';
        const published = source.page_age ? ` · published ${escapeHtml(source.page_age)}` : '';
        const retrieved = formatDate(source.retrieved_at);
        return [
          '<li>',
          `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>`,
          cited,
          `<span class="where">${escapeHtml(sourceHostname(source.url))}${published}`,
          retrieved ? ` · retrieved ${escapeHtml(retrieved)}` : '',
          '</span>',
          '</li>',
        ].join('');
      })
      .join('');

    parts.push(
      '<section class="sources">',
      // "Retrieved", not "Sources": the brief asks the model for a Sources
      // section of its own, and two headings of the same name reading as one
      // list is worse than either. This one is the search tool's record of
      // what was actually fetched, which is a different claim.
      '<h2>Retrieved sources</h2>',
      '<p class="lede">Every page below was retrieved while this report was researched. "Cited" marks one a statement in the report points at.</p>',
      `<ol>${items}</ol>`,
      '</section>',
    );
  }

  parts.push(
    '<footer>',
    'Generated by S3K CRM Market Insights from public sources. AI-assisted research: verify figures and dates against the linked originals before relying on them in a commercial decision.',
    '</footer>',
  );

  return [
    '<!doctype html>',
    '<html lang="en">',
    '<head>',
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<title>${escapeHtml(report.companyName)} — Market Research Report</title>`,
    `<style>${STYLES}</style>`,
    '</head>',
    '<body>',
    `<main class="sheet">${parts.join('\n')}</main>`,
    '</body>',
    '</html>',
    '',
  ].join('\n');
}

/**
 * A filename that survives a downloads folder: `indo-count-market-research.html`.
 *
 * Company names arrive as free text and end up as a path segment, so
 * everything outside `[a-z0-9-]` is folded away rather than escaped.
 */
export function reportFileName(companyName: string, extension: 'html' | 'md'): string {
  const slug = companyName
    .normalize('NFKD')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  return `${slug || 'company'}-market-research.${extension}`;
}
