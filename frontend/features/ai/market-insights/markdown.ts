/**
 * A small Markdown reader for AI-generated reports.
 *
 * Why parse at all, rather than render the text verbatim: §5 asks for a
 * structured report whose sections are driven by the configured prompt, not
 * hard-coded. Splitting on level-two headings gives exactly that — whatever
 * sections the administrator's prompt produced become the sections on screen,
 * and changing the prompt changes the report's structure with no code change.
 *
 * Why hand-written rather than a Markdown library: this output is rendered
 * into a signed-in CRM beside real customer data, and the safe way to render
 * untrusted generated text is to never produce HTML from it at all. This
 * module emits a plain data structure; the components build React elements
 * from it, so there is no `dangerouslySetInnerHTML` anywhere in the feature
 * and no HTML sanitiser to get wrong. It deliberately supports only the
 * constructs the prompt asks for.
 */

/* ------------------------------------------------------------------
   Inline
   ------------------------------------------------------------------ */

export type InlineNode =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'em'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'link'; text: string; href: string };

/** `**bold**`, `*italic*`, `` `code` `` and `[label](https://…)`. */
const INLINE_PATTERN =
  /(\*\*[^*]+\*\*)|(`[^`]+`)|(\[[^\]]+\]\([^)\s]+\))|(\*[^*\n]+\*)|(_[^_\n]+_)/g;

/**
 * Only http(s) links are rendered as links.
 *
 * Generated text can contain any string at all, and `javascript:` in an href
 * is the classic way that becomes an execution vector. Anything else is kept
 * as its label text, so nothing is hidden from the reader — it simply is not
 * clickable.
 */
function safeHref(href: string): string | null {
  const trimmed = href.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : null;
}

export function parseInline(source: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  let cursor = 0;

  for (const match of source.matchAll(INLINE_PATTERN)) {
    const index = match.index ?? 0;
    if (index > cursor) {
      nodes.push({ kind: 'text', text: source.slice(cursor, index) });
    }

    const token = match[0];
    if (token.startsWith('**')) {
      nodes.push({ kind: 'strong', text: token.slice(2, -2) });
    } else if (token.startsWith('`')) {
      nodes.push({ kind: 'code', text: token.slice(1, -1) });
    } else if (token.startsWith('[')) {
      const split = token.indexOf('](');
      const label = token.slice(1, split);
      const href = safeHref(token.slice(split + 2, -1));
      nodes.push(href ? { kind: 'link', text: label, href } : { kind: 'text', text: label });
    } else {
      nodes.push({ kind: 'em', text: token.slice(1, -1) });
    }
    cursor = index + token.length;
  }

  if (cursor < source.length) {
    nodes.push({ kind: 'text', text: source.slice(cursor) });
  }
  return nodes.length > 0 ? nodes : [{ kind: 'text', text: source }];
}

/* ------------------------------------------------------------------
   Blocks
   ------------------------------------------------------------------ */

export type Block =
  | { kind: 'paragraph'; content: InlineNode[] }
  | { kind: 'heading'; level: 3 | 4; content: InlineNode[] }
  | { kind: 'list'; ordered: boolean; items: InlineNode[][] }
  | { kind: 'quote'; content: InlineNode[] };

/** One `## Section` of the report, with the blocks beneath it. */
export interface ReportSection {
  /** Heading text. Empty for content that appeared before any heading. */
  title: string;
  blocks: Block[];
}

const BULLET = /^\s*[-*•]\s+/;
const ORDERED = /^\s*\d+[.)]\s+/;

/**
 * Split Markdown into sections keyed by its level-two headings.
 *
 * Content before the first `##` becomes a leading untitled section, which is
 * where a model's opening summary paragraph normally lands.
 */
export function parseReport(markdown: string): ReportSection[] {
  const sections: ReportSection[] = [];
  let current: ReportSection = { title: '', blocks: [] };
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    current.blocks.push({ kind: 'paragraph', content: parseInline(paragraph.join(' ')) });
    paragraph = [];
  };
  const flushList = () => {
    if (list === null) return;
    current.blocks.push({
      kind: 'list',
      ordered: list.ordered,
      items: list.items.map(parseInline),
    });
    list = null;
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
  };
  const pushSection = () => {
    flushAll();
    if (current.title || current.blocks.length > 0) sections.push(current);
  };

  // Fenced code is not a construct the prompt asks for, but a model may still
  // emit one. Lines inside a fence are passed through as plain paragraphs
  // rather than being parsed, so stray `#` or `-` inside them cannot invent
  // headings and lists.
  let inFence = false;

  for (const rawLine of markdown.replace(/\r\n/g, '\n').split('\n')) {
    const line = rawLine.trimEnd();

    if (line.trimStart().startsWith('```')) {
      inFence = !inFence;
      flushAll();
      continue;
    }
    if (inFence) {
      if (line.trim()) paragraph.push(line.trim());
      continue;
    }

    if (line.trim() === '') {
      flushAll();
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2].trim();
      // H1 and H2 both open a section: a model told to use `##` occasionally
      // reaches for `#` on the document title, and treating that as body text
      // would bury it.
      if (level <= 2) {
        pushSection();
        current = { title: text, blocks: [] };
      } else {
        flushAll();
        current.blocks.push({
          kind: 'heading',
          level: level === 3 ? 3 : 4,
          content: parseInline(text),
        });
      }
      continue;
    }

    if (line.trimStart().startsWith('>')) {
      flushAll();
      current.blocks.push({
        kind: 'quote',
        content: parseInline(line.replace(/^\s*>\s?/, '')),
      });
      continue;
    }

    const bullet = BULLET.exec(line);
    const ordered = ORDERED.exec(line);
    if (bullet || ordered) {
      flushParagraph();
      const isOrdered = ordered !== null;
      if (list === null || list.ordered !== isOrdered) {
        flushList();
        list = { ordered: isOrdered, items: [] };
      }
      list.items.push(line.replace(bullet ? BULLET : ORDERED, '').trim());
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  pushSection();
  return sections;
}

/**
 * The section list as plain text, for the clipboard.
 *
 * Copies the original Markdown rather than a re-render of it: what the user
 * pastes into an email or a deal note should be what the model wrote.
 */
export function firstParagraph(markdown: string, limit = 240): string {
  for (const section of parseReport(markdown)) {
    for (const block of section.blocks) {
      if (block.kind !== 'paragraph') continue;
      const text = block.content.map((node) => node.text).join('').trim();
      if (text.length === 0) continue;
      return text.length > limit ? `${text.slice(0, limit).trimEnd()}…` : text;
    }
  }
  return '';
}
