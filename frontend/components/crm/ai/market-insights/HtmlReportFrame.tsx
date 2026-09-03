'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { asHtmlDocument } from '@/features/ai/market-insights/html-report';

/* ============================================================
   HTML REPORT FRAME

   Renders a report the model wrote as an HTML document.

   The rest of this feature never turns model output into
   markup, and that rule has not been relaxed — it has been
   moved. Nothing here is injected into the CRM's DOM. The
   document is handed to an iframe as `srcdoc`, where it is
   parsed inside its own browsing context and can style itself
   however the prompt asked without reaching anything.

   **What the sandbox allows, and why.** `allow-same-origin` is
   present; `allow-scripts` deliberately is not. Scripts are the
   capability that makes untrusted markup dangerous, and with
   them off, no `<script>`, inline handler or `javascript:` URL
   in the document executes at all. What same-origin buys is the
   ability for this component to read the rendered height, which
   is the only way to size the frame to its content without a
   script inside cooperating. The combination the security
   guidance warns about is same-origin *plus* scripts, because
   that lets the frame escape its own sandbox; one without the
   other does not.

   Two further capabilities are withheld by omission and worth
   naming: no `allow-forms`, so a document cannot present
   something that posts anywhere, and no `allow-top-navigation`,
   so it cannot move the CRM tab somewhere else. Links carry
   `target="_blank"` via a base tag, so a reader clicking a
   source still gets a new tab.
   ============================================================ */

/** Frame height before measurement, and the floor afterwards. */
const INITIAL_HEIGHT = 900;
/** Ceiling. A runaway document scrolls inside the frame instead of the page. */
const MAX_HEIGHT = 20000;

export default function HtmlReportFrame({ html }: { html: string }) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(INITIAL_HEIGHT);

  const measure = useCallback(() => {
    const document_ = frameRef.current?.contentDocument;
    if (!document_?.documentElement) return;
    // `scrollHeight` on the root element rather than the body: a document whose
    // body is `height: 100%` reports its viewport height from `body`, which
    // would collapse the frame to a sliver.
    const measured = Math.max(
      document_.documentElement.scrollHeight,
      document_.body?.scrollHeight ?? 0,
    );
    if (measured > 0) setHeight(Math.min(Math.max(measured + 8, 200), MAX_HEIGHT));
  }, []);

  // Re-measure after load, then again shortly after: web fonts and images
  // settle a beat later and change the height when they do.
  useEffect(() => {
    const timers = [80, 400, 1200].map((delay) => setTimeout(measure, delay));
    return () => timers.forEach(clearTimeout);
  }, [measure, html]);

  return (
    <div className="surface bd overflow-hidden rounded-2xl border">
      <iframe
        ref={frameRef}
        onLoad={measure}
        title="Market intelligence report"
        // No allow-scripts. See the header comment.
        sandbox="allow-same-origin allow-popups"
        srcDoc={withLinkTarget(asHtmlDocument(html))}
        className="w-full border-0 bg-white"
        style={{ height, colorScheme: 'light' }}
      />
    </div>
  );
}

/**
 * Make the document's links open in a new tab.
 *
 * Injected as a `<base>` rather than by rewriting anchors, so the model's
 * markup is not edited — the report a reader sees is the document the model
 * produced. Without this, a source link would try to navigate the frame and,
 * with no `allow-top-navigation`, simply do nothing.
 */
function withLinkTarget(document_: string): string {
  const base = '<base target="_blank">';
  if (/<base[\s>]/i.test(document_)) return document_;
  return /<head[\s>]/i.test(document_)
    ? document_.replace(/<head([\s>])/i, `<head$1${base}`)
    : document_.replace(/<html([\s>])/i, `<html$1<head>${base}</head>`);
}
