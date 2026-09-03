'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, FileCode2, FileText, Printer, type LucideIcon } from 'lucide-react';
import { toast } from 'sonner';

import { cn } from '@/lib/utils';
import { saveBlob } from '@/lib/save-file';
import {
  buildReportHtml,
  reportFileName,
  type ReportDocument,
} from '@/features/ai/market-insights/export-html';

/* ============================================================
   DOWNLOAD REPORT

   Takes the finished report out of the CRM.

   Three ways out, because they are wanted for different
   reasons: the HTML document is the thing you attach to an
   email before a CXO meeting, the Markdown is the thing you
   paste into a deal note or a wiki, and printing is how the
   same document becomes a PDF without this app shipping a PDF
   engine.

   All of it happens in the browser. The report is already on
   this page, so an export endpoint would be a round trip to
   fetch text we are holding, plus a second place for the
   document's layout to live.
   ============================================================ */

/** How long to leave the print iframe attached after the dialog is dismissed. */
const PRINT_CLEANUP_MS = 60_000;

function MenuItem({
  icon: Icon,
  label,
  hint,
  onSelect,
}: {
  icon: LucideIcon;
  label: string;
  hint: string;
  onSelect: () => void;
}) {
  return (
    <button
      role="menuitem"
      type="button"
      onClick={onSelect}
      className="hover:surface-2 focus-visible:surface-2 flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors focus-visible:outline-none"
    >
      <Icon
        className="mt-0.5 h-3.5 w-3.5 shrink-0"
        style={{ color: 'var(--accent)' }}
        aria-hidden="true"
      />
      <span className="min-w-0">
        <span className="txt block text-[12.5px] font-semibold">{label}</span>
        <span className="txt-faint mt-0.5 block text-[11.5px] leading-snug">{hint}</span>
      </span>
    </button>
  );
}

/** Menu width, in px. Kept in step with the `w-64` on the panel. */
const MENU_WIDTH = 256;

export default function DownloadReportMenu({ report }: { report: ReportDocument }) {
  const [open, setOpen] = useState(false);
  // Right-aligned by default, because the trigger lives in a right-aligned
  // action row. On a narrow viewport that same alignment pushes the panel off
  // the left edge and takes the icons with it, so it flips when there is not
  // room — measured rather than guessed at a breakpoint, since what matters is
  // where this button actually sits, not how wide the window is.
  const [alignLeft, setAlignLeft] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const cleanupTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A print frame outlives the click that made it, so it has to be torn down
  // if the report is closed or the page navigates while the dialog is open.
  useEffect(
    () => () => {
      if (cleanupTimer.current) clearTimeout(cleanupTimer.current);
      frameRef.current?.remove();
    },
    [],
  );

  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open]);

  const downloadHtml = useCallback(() => {
    const html = buildReportHtml(report);
    saveBlob(
      new Blob([html], { type: 'text/html;charset=utf-8' }),
      reportFileName(report.companyName, 'html'),
    );
    toast.success('Report downloaded');
  }, [report]);

  const downloadMarkdown = useCallback(() => {
    saveBlob(
      new Blob([report.markdown], { type: 'text/markdown;charset=utf-8' }),
      reportFileName(report.companyName, 'md'),
    );
    toast.success('Markdown downloaded');
  }, [report]);

  const print = useCallback(() => {
    // An off-screen iframe rather than a new window: a popup blocker stops
    // `window.open` on a click this far from the user's gesture, and printing
    // the CRM page itself would print the sidebar with it.
    frameRef.current?.remove();
    if (cleanupTimer.current) clearTimeout(cleanupTimer.current);

    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.setAttribute('title', 'Report for printing');
    frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
    frame.srcdoc = buildReportHtml(report);

    frame.addEventListener('load', () => {
      const view = frame.contentWindow;
      if (!view) {
        toast.error('Could not open the print dialog.');
        frame.remove();
        return;
      }
      view.focus();
      view.print();
    });

    document.body.appendChild(frame);
    frameRef.current = frame;
    // Removing the frame the moment `print()` returns cancels the dialog in
    // some browsers, so it is left in place and swept up later.
    cleanupTimer.current = setTimeout(() => {
      frame.remove();
      if (frameRef.current === frame) frameRef.current = null;
    }, PRINT_CLEANUP_MS);
  }, [report]);

  const select = useCallback((run: () => void) => {
    setOpen(false);
    run();
  }, []);

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Download this report"
        onClick={() => {
          const rect = triggerRef.current?.getBoundingClientRect();
          // 8px of breathing room, so the panel never touches the edge.
          if (rect) setAlignLeft(rect.right - MENU_WIDTH < 8);
          setOpen((current) => !current);
        }}
        className={cn(
          'ctl txt-muted inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold transition hover:opacity-80',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
        )}
      >
        <Download className="h-3.5 w-3.5" aria-hidden="true" />
        Download
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            role="menu"
            aria-label="Download report"
            className={cn(
              'surface bd absolute top-full z-20 mt-1 w-64 max-w-[calc(100vw-1rem)] overflow-hidden rounded-xl border shadow-lg',
              alignLeft ? 'left-0' : 'right-0',
            )}
          >
            <MenuItem
              icon={FileCode2}
              label="HTML report"
              hint="Formatted document, opens anywhere"
              onSelect={() => select(downloadHtml)}
            />
            <MenuItem
              icon={FileText}
              label="Markdown"
              hint="Plain text, for notes and wikis"
              onSelect={() => select(downloadMarkdown)}
            />
            <MenuItem
              icon={Printer}
              label="Print or save as PDF"
              hint="Opens your print dialog"
              onSelect={() => select(print)}
            />
          </div>
        </>
      )}
    </div>
  );
}
