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
}: {
  blocks: Block[];
  className?: string;
}) {
  return (
    <div className={cn('space-y-3', className)}>
      {blocks.map((block, index) => {
        switch (block.kind) {
          case 'heading':
            return (
              <h4
                key={index}
                className={cn(
                  'txt font-display font-bold',
                  block.level === 3 ? 'text-[13.5px]' : 'text-[12.5px]',
                )}
              >
                <Inline nodes={block.content} />
              </h4>
            );

          case 'list':
            return block.ordered ? (
              <ol key={index} className="txt-muted ml-4 list-decimal space-y-1.5 text-[13px] leading-relaxed">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="pl-1">
                    <Inline nodes={item} />
                  </li>
                ))}
              </ol>
            ) : (
              <ul key={index} className="txt-muted ml-4 list-disc space-y-1.5 text-[13px] leading-relaxed">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="pl-1">
                    <Inline nodes={item} />
                  </li>
                ))}
              </ul>
            );

          case 'quote':
            return (
              <blockquote
                key={index}
                className="txt-muted border-l-2 pl-3 text-[13px] italic leading-relaxed"
                style={{ borderColor: 'var(--accent)' }}
              >
                <Inline nodes={block.content} />
              </blockquote>
            );

          default:
            return (
              <p key={index} className="txt-muted text-[13px] leading-relaxed">
                <Inline nodes={block.content} />
              </p>
            );
        }
      })}
    </div>
  );
}
