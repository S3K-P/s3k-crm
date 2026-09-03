'use client';

import { useMemo } from 'react';

import MarkdownContent from '@/components/crm/ai/market-insights/MarkdownContent';
import HtmlReportFrame from '@/components/crm/ai/market-insights/HtmlReportFrame';
import { parseReport } from '@/features/ai/market-insights/markdown';
import { looksLikeHtmlDocument, unfence } from '@/features/ai/market-insights/html-report';

/* ============================================================
   REPORT VIEW

   The Market Intelligence Report, as one continuous document.

   It reads top to bottom the way a chat assistant's answer
   does — headings, prose, bullets and tables in the order the
   model wrote them — rather than as cards in a grid. Two
   reasons, and the second is the load-bearing one:

   1. This is a two-to-three page report meant to be *read*
      before a meeting, not a dashboard to be scanned.
   2. The sections are whatever level-two headings the
      configured prompt produced (§5). A layout that assigns
      each section a card, an icon and a collapsed/expanded
      default is quietly asserting it knows what the sections
      are. Flowing text makes no such claim, so an administrator
      who rewrites the prompt in AI Settings gets a report that
      still reads correctly.

   Copy and Download live once, in the header above this — the
   same place a chat UI puts them, and the reason there is no
   per-section action here.
   ============================================================ */

export default function ReportView({
  markdown,
  companyName,
}: {
  markdown: string;
  /** Present for callers and future use; the document titles itself. */
  companyName?: string;
}) {
  void companyName;

  // The configured prompt decides the format, so the renderer follows it
  // rather than the other way round. A prompt asking for an HTML file gets one
  // and it is shown as a document; the shipped brief asks for Markdown and
  // flows below. Getting this wrong is what turns a report into a screenful of
  // raw `<!doctype html>`.
  const content = useMemo(() => unfence(markdown), [markdown]);
  const isHtml = useMemo(() => looksLikeHtmlDocument(content), [content]);

  const sections = useMemo(() => (isHtml ? [] : parseReport(content)), [content, isHtml]);

  if (isHtml) return <HtmlReportFrame html={content} />;

  return (
    <article className="surface bd rounded-2xl border px-5 py-6 sm:px-8 sm:py-8">
      {/* Capped for line length: prose at the full width of a wide monitor is
          measurably harder to read, and this is a document. */}
      <div className="mx-auto max-w-[44rem]">
        {sections.map((section, index) => (
          <section key={`${section.title}-${index}`}>
            {section.title && (
              <h2
                className={
                  'font-display txt text-[17px] font-extrabold leading-snug tracking-tight ' +
                  // No top margin on the first heading — the card's padding is
                  // already the space above it.
                  (index === 0 ? 'mb-3' : 'mb-3 mt-7')
                }
              >
                {section.title}
              </h2>
            )}
            <MarkdownContent blocks={section.blocks} reading />
          </section>
        ))}
      </div>
    </article>
  );
}
