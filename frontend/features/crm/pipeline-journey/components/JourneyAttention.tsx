'use client';

import { useState } from 'react';
import { AlertTriangle, Flame, Target, TrendingUp, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AttentionItem, AttentionPresetId } from '../types';

/* ============================================================
   WHAT NEEDS ATTENTION
   The AI-prioritised queue. Each card is a cross-stage cut of
   the pipeline and opens that cut in the deals drawer.

   The hover border and shadow are per-card brand colours, so
   they are applied from state rather than as utility classes.
   ============================================================ */

interface JourneyAttentionProps {
  items: AttentionItem[];
  onOpenPreset: (preset: AttentionPresetId) => void;
}

const ICONS: Record<AttentionPresetId, LucideIcon> = {
  stuck: AlertTriangle,
  closing: Flame,
  growth: TrendingUp,
  ontrack: Target,
};

export default function JourneyAttention({ items, onOpenPreset }: JourneyAttentionProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <section
      className="surface bd anim-fade-up rounded-[28px] border px-7 py-[26px]"
      style={{ boxShadow: 'var(--shadow-card)', animationDelay: '0.28s' }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="txt font-display text-[19px] font-extrabold tracking-[-0.02em]">
            What Needs Attention
          </h2>
          <p className="txt-muted mt-[5px] text-[12.5px] font-medium">
            Four things worth your next hour
          </p>
        </div>
        <span
          className="rounded-full px-[11px] py-[5px] text-[11.5px] font-extrabold"
          style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
        >
          AI prioritised
        </span>
      </div>

      <div className="mt-[18px] grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
        {items.map(item => {
          const Icon = ICONS[item.preset];
          const isHovered = hovered === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onOpenPreset(item.preset)}
              onMouseEnter={() => setHovered(item.id)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(item.id)}
              onBlur={() => setHovered(null)}
              className="surface-2 bd flex items-start gap-[13px] rounded-[20px] border p-4 text-left outline-none transition-[transform,box-shadow,border-color] duration-200"
              style={{
                transform: isHovered ? 'translateY(-3px)' : undefined,
                borderColor: isHovered ? item.hoverBorder : undefined,
                boxShadow: isHovered ? item.hoverShadow : undefined,
              }}
            >
              <span
                className={cn(
                  'grid h-[38px] w-[38px] shrink-0 place-items-center rounded-xl bg-gradient-to-br',
                  item.gradient,
                )}
              >
                <Icon className="h-[18px] w-[18px] text-white" strokeWidth={1.9} />
              </span>
              <span className="min-w-0">
                <span className="txt block text-[13.5px] font-bold tracking-[-0.01em]">
                  {item.title}
                </span>
                <span className="txt-muted mt-1 block text-[12px] font-medium">{item.detail}</span>
                <span
                  className="mt-[7px] block text-[12px] font-bold"
                  style={{ color: 'var(--accent)' }}
                >
                  {item.cta}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
