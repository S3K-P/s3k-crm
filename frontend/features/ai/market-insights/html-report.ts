/**
 * Recognising a report the model wrote as HTML rather than Markdown.
 *
 * The configured prompt decides the output format (§5, §11). The brief this
 * codebase ships asks for Markdown, but an administrator is free to replace it
 * — and a prompt asking for "a single polished HTML file with embedded CSS" is
 * a reasonable thing to want, because that is what gets emailed before a
 * meeting. When that happens the model returns a whole `<!doctype html>`
 * document, and rendering it through the Markdown reader prints the source as
 * prose: tags, CSS and all.
 *
 * So the renderer has to be able to tell the two apart. This module is that
 * test, and nothing more — it makes no attempt to sanitise, rewrite or parse
 * the HTML. Isolation is the frame's job (see `HtmlReportFrame`), because the
 * safe way to show untrusted markup is to deny it capabilities, not to try to
 * clean it.
 */

/** A document opener, allowing for a leading BOM, comments or whitespace. */
const DOCUMENT_START = /^\s*(?:<!--[\s\S]*?-->\s*)*(?:<!doctype\s+html|<html[\s>])/i;

/** A fragment that is plainly markup rather than prose with a stray angle bracket. */
const STRUCTURAL_TAG = /<(?:style|section|article|div|table|header|main|h[1-6])[\s>]/i;

/**
 * Whether this report body should be rendered as HTML.
 *
 * Deliberately conservative in one direction only: a false negative renders an
 * HTML report as Markdown, which looks wrong but shows every word. A false
 * positive would take a Markdown report — the normal case — and hand it to a
 * frame that renders it as a wall of unstyled text, which is worse. So a bare
 * `<div>` mentioned inside a Markdown report is not enough; the content has to
 * either open as a document or be markup-shaped throughout.
 */
export function looksLikeHtmlDocument(content: string): boolean {
  const trimmed = content.trim();
  if (!trimmed) return false;
  if (DOCUMENT_START.test(trimmed)) return true;

  // No document wrapper: accept only if it both opens as a tag and carries
  // real structure, so prose containing "<html>" in passing does not qualify.
  if (!trimmed.startsWith('<')) return false;
  if (!STRUCTURAL_TAG.test(trimmed)) return false;

  // Markdown headings are the tell-tale of a Markdown report that merely
  // embeds some markup. If they are present, treat it as Markdown.
  return !/^#{1,3}\s+\S/m.test(trimmed);
}

/**
 * Wrap a bare HTML fragment into a document, leaving a real one untouched.
 *
 * A model told to emit "an HTML report" sometimes returns only the body's
 * markup. Given to an iframe as-is that still renders, but with the browser's
 * default margins and no charset, so em dashes and rupee signs arrive as
 * mojibake.
 */
export function asHtmlDocument(content: string): string {
  const trimmed = content.trim();
  if (DOCUMENT_START.test(trimmed)) return trimmed;
  return [
    '<!doctype html>',
    '<html><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '</head><body>',
    trimmed,
    '</body></html>',
  ].join('\n');
}

/**
 * Strip an accidental Markdown code fence from around an HTML document.
 *
 * Models asked for a file frequently deliver it fenced as ```html … ```, which
 * is a helpful habit in a chat window and a rendering bug here.
 */
export function unfence(content: string): string {
  const fenced = /^\s*```(?:html)?\s*\n([\s\S]*?)\n?\s*```\s*$/i.exec(content);
  return fenced ? fenced[1] : content;
}
