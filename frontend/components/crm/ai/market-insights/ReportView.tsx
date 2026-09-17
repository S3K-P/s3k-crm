'use client';

import { useMemo } from 'react';
import {
  AlertTriangle,
  Banknote,
  Boxes,
  Building2,
  CalendarClock,
  Compass,
  FileText,
  Factory,
  Gauge,
  Handshake,
  Lightbulb,
  ListChecks,
  Swords,
  TrendingUp,
  Users,
  type LucideIcon,
} from 'lucide-react';

import InsightSection from '@/components/crm/ai/shared/InsightSection';
import CopyButton from '@/components/crm/ai/shared/CopyButton';
import MarkdownContent from '@/components/crm/ai/market-insights/MarkdownContent';
import { parseReport } from '@/features/ai/market-insights/markdown';

/* ============================================================
   REPORT VIEW

   The Market Intelligence Report.

   The sections are NOT hard-coded. They are whatever level-two
   headings the configured prompt caused the model to write, so
   an administrator who edits the prompt in AI Settings changes
   the shape of this page without anybody touching this file
   (§5). The map below only assigns an icon to headings that
   happen to be recognisable; an unrecognised section renders
   perfectly well with the default one.
   ============================================================ */

/** Keyword → icon. Matched loosely, purely cosmetic. */
const SECTION_ICONS: ReadonlyArray<readonly [string, LucideIcon]> = [
  ['overview', Building2],
  ['industry', Factory],
  ['product', Boxes],
  ['service', Boxes],
  ['market position', Gauge],
  ['business model', Compass],
  ['customer', Handshake],
  ['competitor', Swords],
  ['recent', CalendarClock],
  ['development', CalendarClock],
  ['leadership', Users],
  ['people', Users],
  ['financial', Banknote],
  ['revenue', Banknote],
  ['opportunit', Lightbulb],
  ['risk', AlertTriangle],
  ['challenge', AlertTriangle],
  ['sales relevance', TrendingUp],
  ['next action', ListChecks],
  ['recommend', ListChecks],
  ['summary', FileText],
];

function iconFor(title: string): LucideIcon {
  const normalised = title.toLowerCase();
  for (const [keyword, icon] of SECTION_ICONS) {
    if (normalised.includes(keyword)) return icon;
  }
  return FileText;
}

/** One-line preview shown in a collapsed section header. */
function summarise(blocks: ReturnType<typeof parseReport>[number]['blocks']): string {
  for (const block of blocks) {
    if (block.kind === 'paragraph' || block.kind === 'quote') {
      const text = block.content.map((node) => node.text).join('').trim();
      if (text) return text.length > 120 ? `${text.slice(0, 120).trimEnd()}…` : text;
    }
    if (block.kind === 'list' && block.items.length > 0) {
      return `${block.items.length} point${block.items.length === 1 ? '' : 's'}`;
    }
  }
  return '';
}

export default function ReportView({
  markdown,
  companyName,
}: {
  markdown: string;
  companyName: string;
}) {
  const sections = useMemo(() => parseReport(markdown), [markdown]);

  // Content the model wrote before its first heading — usually an opening
  // summary. Rendered above the cards rather than inside one, because it
  // introduces the report rather than being a section of it.
  const lead = sections.find((section) => section.title === '');
  const titled = sections.filter((section) => section.title !== '');

  return (
    <div className="space-y-4">
      {lead && lead.blocks.length > 0 && (
        <div className="surface bd rounded-2xl border p-4 sm:p-5">
          <MarkdownContent blocks={lead.blocks} />
        </div>
      )}

      {titled.length === 0 && !lead && (
        // A report with no headings at all is unusual but not an error — the
        // prompt may simply not ask for them. Show the prose rather than an
        // empty page.
        <div className="surface bd rounded-2xl border p-4 sm:p-5">
          <MarkdownContent blocks={parseReport(markdown).flatMap((s) => s.blocks)} />
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {titled.map((section, index) => (
          <InsightSection
            key={`${section.title}-${index}`}
            icon={iconFor(section.title)}
            title={section.title}
            summary={summarise(section.blocks)}
            // The first four open, the rest collapsed: a fourteen-section
            // report fully expanded is a wall of text nobody scrolls.
            defaultOpen={index < 4}
            action={
              <CopyButton
                value={sectionMarkdown(markdown, section.title)}
                label={`${section.title} for ${companyName}`}
              />
            }
          >
            <MarkdownContent blocks={section.blocks} />
          </InsightSection>
        ))}
      </div>
    </div>
  );
}

/**
 * The original Markdown of one section, for the clipboard.
 *
 * Sliced out of the source rather than re-serialised from the parse tree: what
 * someone pastes into an email should be exactly what the model wrote.
 */
function sectionMarkdown(markdown: string, title: string): string {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const start = lines.findIndex(
    (line) => /^#{1,2}\s+/.test(line) && line.replace(/^#{1,2}\s+/, '').trim() === title,
  );
  if (start === -1) return markdown;

  const rest = lines.slice(start + 1);
  const end = rest.findIndex((line) => /^#{1,2}\s+/.test(line));
  return [lines[start], ...(end === -1 ? rest : rest.slice(0, end))].join('\n').trim();
}
