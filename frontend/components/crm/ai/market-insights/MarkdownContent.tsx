'use client';

import { Fragment } from 'react';

import { cn } from '@/lib/utils';
import type { Block, InlineNode } from '@/features/ai/market-insights/markdown';

/* ============================================================
   MARKDOWN CONTENT

   Renders the parsed blocks from `features/ai/market-insights/
   markdown` as React elements.

   Every node becomes a real element — there is no
   `dangerouslySetInnerHTML` anywhere in this feature. Model
   output is untrusted text rendered inside a signed-in CRM, so
   it never becomes markup. Links were filtered to http(s) at
   parse time and carry `noopener`.
   ============================================================ */

function Inline({ nodes }: { nodes: InlineNode[] }) {
  return (
    <>
      {nodes.map((node, index) => {
        switch (node.kind) {
          case 'strong':
            return (
              <strong key={index} className="txt font-semibold">
                {node.text}
              </strong>
            );
          case 'em':
            return (
              <em key={index} className="italic">
                {node.text}
              </em>
            );
          case 'code':
            return (
              <code
                key={index}
                className="surface-2 bd rounded border px-1 py-0.5 font-mono text-[11.5px]"
              >
                {node.text}
              </code>
            );
          case 'link':
            return (
              <a
                key={index}
                href={node.href}
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-dotted underline-offset-2 hover:opacity-80"
                style={{ color: 'var(--accent)' }}
              >
                {node.text}
              </a>
            );
          default:
            return <Fragment key={index}>{node.text}</Fragment>;
        }
      })}
    </>
  );
}

export default function MarkdownContent({
  blocks,
  className,
  /**
   * Type scale. The default is the compact one a follow-up bubble wants; the
   * report reads as a document, so it asks for `reading` — a step up in size
   * and line height, which is the difference between skimming a card and
   * actually reading two pages of prose.
   */
  reading = false,
}: {
  blocks: Block[];
  className?: string;
  reading?: boolean;
}) {
  const body = reading ? 'text-[14px] leading-[1.75]' : 'text-[13px] leading-relaxed';

  return (
    <div className={cn(reading ? 'space-y-4' : 'space-y-3', className)}>
      {blocks.map((block, index) => {
        switch (block.kind) {
          case 'heading':
            return (
              <h4
                key={index}
                className={cn(
                  'txt font-display font-bold',
                  reading ? 'pt-1' : '',
                  block.level === 3
                    ? reading
                      ? 'text-[15px]'
                      : 'text-[13.5px]'
                    : reading
                      ? 'text-[14px]'
                      : 'text-[12.5px]',
                )}
              >
                <Inline nodes={block.content} />
              </h4>
            );

          case 'list':
            return block.ordered ? (
              <ol
                key={index}
                className={cn('txt-muted ml-5 list-decimal space-y-2', body)}
              >
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="pl-1">
                    <Inline nodes={item} />
                  </li>
                ))}
              </ol>
            ) : (
              <ul key={index} className={cn('txt-muted ml-5 list-disc space-y-2', body)}>
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="pl-1">
                    <Inline nodes={item} />
                  </li>
                ))}
              </ul>
            );

          case 'table':
            return (
              // The scroll container is the table's own, not the page's: a
              // six-column competitor comparison must not make the whole
              // report scroll sideways on a laptop.
              <div key={index} className="bd -mx-1 overflow-x-auto rounded-xl border">
                <table
                  className={cn(
                    'w-full border-collapse',
                    reading ? 'text-[13px]' : 'text-[12.5px]',
                  )}
                >
                  <thead>
                    <tr className="surface-2">
                      {block.headers.map((header, column) => (
                        <th
                          key={column}
                          scope="col"
                          className={cn(
                            'bd txt border-b text-left font-semibold',
                            reading ? 'px-3.5 py-2.5' : 'px-3 py-2',
                          )}
                          style={{ textAlign: block.align[column] }}
                        >
                          <Inline nodes={header} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {block.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {row.map((cell, column) => (
                          <td
                            key={column}
                            className={cn(
                              'txt-muted align-top leading-relaxed',
                              reading ? 'px-3.5 py-2.5' : 'px-3 py-2',
                            )}
                            style={{ textAlign: block.align[column] }}
                          >
                            <Inline nodes={cell} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );

          case 'quote':
            return (
              <blockquote
                key={index}
                className={cn('txt-muted border-l-2 italic', reading ? 'pl-4' : 'pl-3', body)}
                style={{ borderColor: 'var(--accent)' }}
              >
                <Inline nodes={block.content} />
              </blockquote>
            );

          default:
            return (
              <p key={index} className={cn('txt-muted', body)}>
                <Inline nodes={block.content} />
              </p>
            );
        }
      })}
    </div>
  );
}
